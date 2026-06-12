from __future__ import annotations

import asyncio
import logging
import random
import re
from collections import OrderedDict
from collections.abc import Callable
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from andino.agent_builder import build_agent
from andino.config import AgentConfig
from andino.log_context import bind_task, clear_task

logger = logging.getLogger(__name__)

MAX_HISTORY = 100


class TaskState(str, Enum):
    queued = "queued"
    running = "running"
    interrupted = "interrupted"
    completed = "completed"
    failed = "failed"
    timeout = "timeout"


class TaskStatus(BaseModel):
    task_id: str
    status: TaskState
    prompt: str = ""
    session_id: str | None = None
    result: str | None = None
    structured_output: dict[str, Any] | None = None
    error: str | None = None
    interrupts: list[dict[str, Any]] | None = None
    workspace_dir: str | None = None
    created_at: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    # Token accounting (extracted from AgentResult.metrics on completion)
    input_tokens: int = 0
    output_tokens: int = 0


class _TaskItem:
    """Internal queue item."""

    __slots__ = ("prompt", "session_id", "task_id")

    def __init__(self, task_id: str, prompt: str, session_id: str | None) -> None:
        self.task_id = task_id
        self.prompt = prompt
        self.session_id = session_id


class AgentPool:
    """LRU cache of Agent instances keyed by session_id."""

    def __init__(self, config: AgentConfig) -> None:
        self._config = config
        self._max_size = config.session.max_pool_size
        self._cache: OrderedDict[str | None, object] = OrderedDict()
        self._locks: dict[str | None, asyncio.Lock] = {}
        # Stateless (shared) agent — always in cache
        self._cache[None] = build_agent(config, session_id=None)

    def _get_lock(self, session_id: str | None) -> asyncio.Lock:
        if session_id not in self._locks:
            self._locks[session_id] = asyncio.Lock()
        return self._locks[session_id]

    async def acquire(self, session_id: str | None):
        """Get agent + lock for a session. Returns (agent, lock) context."""
        lock = self._get_lock(session_id)
        await lock.acquire()

        if session_id is None:
            return self._cache[None], lock

        if session_id in self._cache:
            self._cache.move_to_end(session_id)
            return self._cache[session_id], lock

        # Evict LRU if full (skip None key)
        while len(self._cache) > self._max_size:
            oldest_key = next(k for k in self._cache if k is not None)
            del self._cache[oldest_key]
            self._locks.pop(oldest_key, None)
            logger.info("pool_evict session_id=%s", oldest_key)

        agent = build_agent(self._config, session_id=session_id)
        self._cache[session_id] = agent
        return agent, lock


_THINKING_RE = re.compile(r"<thinking>.*?</thinking>", re.DOTALL)


def _strip_thinking(text: str) -> str:
    """Remove ``<thinking>...</thinking>`` blocks from model output.

    Some models (e.g. Amazon Nova) embed reasoning in plain-text
    ``<thinking>`` tags instead of using the native reasoning content
    block type.  This helper strips those tags so they don't leak into
    the user-facing response.
    """
    cleaned = _THINKING_RE.sub("", text)
    # Collapse any leftover leading/trailing whitespace
    return cleaned.strip()


def _extract_text(result: object) -> str:
    """Extract text output from an AgentResult."""
    if hasattr(result, "message"):
        msg = result.message
        if isinstance(msg, dict):
            content = msg.get("content", [])
            texts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("text")]
            return _strip_thinking("\n".join(texts))
        return _strip_thinking(str(msg))
    return _strip_thinking(str(result))


def _is_transient(exc: Exception) -> bool:
    """Heuristic for retry-worthy failures.

    Network-level httpx errors and provider throttling retry; anything else
    (validation, auth, tool bugs) fails fast. Bedrock throttling is detected
    by string match so botocore stays an optional dependency.
    """
    try:
        import httpx
        if isinstance(exc, (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError)):
            return True
    except ImportError:  # pragma: no cover
        pass
    if isinstance(exc, ConnectionError):
        return True
    text = f"{type(exc).__name__}: {exc}"
    return any(
        marker in text
        for marker in ("ThrottlingException", "TooManyRequestsException", "ServiceUnavailable", "throttl")
    )


async def _consume_stream(agent: Any, input_data: Any, on_progress: Callable | None) -> Any:
    """Consume an ``agent.stream_async`` iterator and return the final ``AgentResult``.

    When ``on_progress`` is provided, it is awaited with each text delta as
    the stream produces tokens. Interrupt handling and the final result are
    delivered identically to ``invoke_async`` (which itself wraps
    ``stream_async`` internally).
    """
    result = None
    async for event in agent.stream_async(input_data):
        if on_progress is not None and isinstance(event, dict) and "data" in event:
            delta = event["data"]
            if delta:
                try:
                    await on_progress(delta)
                except Exception:
                    logger.exception("on_progress_callback_failed")
        if isinstance(event, dict) and "result" in event:
            result = event["result"]
    if result is None:
        raise RuntimeError("agent stream ended without an AgentResult event")
    return result


class TaskExecutor:
    """Queue-based task executor using ``stream_async`` under the hood."""

    def __init__(self, config: AgentConfig) -> None:
        self._config = config
        self._limits = config.limits
        self._pool = AgentPool(config)
        max_queued = config.limits.max_concurrent_tasks * 2
        self._queue: asyncio.Queue[_TaskItem] = asyncio.Queue(maxsize=max_queued)
        self._tasks: OrderedDict[str, TaskStatus] = OrderedDict()
        self._workers: list[asyncio.Task] = []
        self._started = False
        self._completion_events: dict[str, asyncio.Event] = {}
        self._pending_responses: dict[str, asyncio.Future[list[dict]]] = {}
        self._interrupt_callbacks: dict[str, Callable] = {}
        self._progress_callbacks: dict[str, Callable] = {}
        # Usage JSONL + approvals live next to the agent's other state.
        from andino.home import resolve_agent_dir
        self._agent_dir = resolve_agent_dir(config.name)
        self._usage_file = self._agent_dir / "usage.jsonl"

    def ensure_started(self) -> None:
        """Start worker coroutines. Safe to call multiple times."""
        if self._started:
            return
        self._started = True
        for i in range(self._limits.max_concurrent_tasks):
            task = asyncio.create_task(self._worker(i))
            self._workers.append(task)
        logger.info("workers_started count=%d", self._limits.max_concurrent_tasks)

    @property
    def running_count(self) -> int:
        return sum(1 for t in self._tasks.values() if t.status == TaskState.running)

    async def submit(self, task_id: str, prompt: str, session_id: str | None = None) -> TaskStatus:
        """Enqueue a task. Raises ValueError if queue is full."""
        self.ensure_started()

        now = datetime.now(UTC).isoformat()
        status = TaskStatus(
            task_id=task_id,
            status=TaskState.queued,
            prompt=prompt,
            session_id=session_id,
            created_at=now,
        )
        self._tasks[task_id] = status
        self._trim_history()

        try:
            self._queue.put_nowait(_TaskItem(task_id, prompt, session_id))
        except asyncio.QueueFull:
            status.status = TaskState.failed
            status.error = "Queue full — try again later"
            raise ValueError("Task queue is full. Try again later.") from None

        return status

    async def submit_and_wait(
        self, task_id: str, prompt: str, session_id: str | None = None
    ) -> TaskStatus:
        """Submit a task and wait for it to complete. Used by channels."""
        event = asyncio.Event()
        self._completion_events[task_id] = event
        await self.submit(task_id, prompt, session_id)
        await event.wait()
        self._completion_events.pop(task_id, None)
        return self._tasks[task_id]

    async def _worker(self, worker_id: int) -> None:
        """Worker coroutine that consumes tasks from the queue."""
        logger.info("worker_started id=%d", worker_id)
        while True:
            item = await self._queue.get()
            task_status = self._tasks.get(item.task_id)
            if task_status is None:
                self._queue.task_done()
                continue

            # Bind the task id to the logging context — every record emitted
            # from here until teardown carries [task=<id>] (see log_context).
            bind_task(item.task_id)

            task_status.status = TaskState.running
            task_status.started_at = datetime.now(UTC).isoformat()

            # Populate workspace_dir if workspace is enabled for this session
            if self._config.workspace.enabled and item.session_id:
                workspace = Path(self._config.workspace.base_dir).resolve() / item.session_id
                task_status.workspace_dir = str(workspace)

            agent, lock = await self._pool.acquire(item.session_id)
            on_progress = self._progress_callbacks.get(item.task_id)
            try:
                input_data: Any = item.prompt
                while True:
                    # Retry transient failures (network blips, throttling)
                    # with jittered exponential backoff. The task budget
                    # (asyncio.wait_for TimeoutError) is NEVER retried — it
                    # propagates to the timeout branch below.
                    max_retries = getattr(self._limits, "max_retries", 2)
                    attempt = 0
                    while True:
                        try:
                            result = await asyncio.wait_for(
                                _consume_stream(agent, input_data, on_progress),
                                timeout=self._limits.task_timeout_seconds,
                            )
                            break
                        except TimeoutError:
                            raise  # task budget exhausted — not transient
                        except Exception as exc:
                            if attempt >= max_retries or not _is_transient(exc):
                                raise
                            attempt += 1
                            delay = 2 ** (attempt - 1) + random.random()
                            logger.warning(
                                "task_retry attempt=%d/%d delay=%.1fs error=%s",
                                attempt, max_retries, delay, str(exc)[:200],
                            )
                            await asyncio.sleep(delay)

                    # Check for interrupt
                    if result.stop_reason == "interrupt" and result.interrupts:
                        task_status.status = TaskState.interrupted
                        task_status.interrupts = [
                            {
                                "interrupt_id": intr.id,
                                "name": intr.name,
                                "reason": intr.reason,
                            }
                            for intr in result.interrupts
                        ]
                        logger.info(
                            "task_interrupted task_id=%s tools=%s",
                            item.task_id,
                            [i["name"] for i in task_status.interrupts],
                        )

                        # Persist the pending approval so it survives a
                        # process restart (file-backed replay — see approvals).
                        from andino import approvals as _approvals
                        _approvals.save_pending(
                            self._agent_dir,
                            task_id=item.task_id,
                            session_id=item.session_id,
                            prompt=item.prompt,
                            interrupts=task_status.interrupts,
                        )

                        # Notify channel callback if registered
                        cb = self._interrupt_callbacks.pop(item.task_id, None)
                        if cb is not None:
                            await cb(task_status)

                        # Wait for human response
                        loop = asyncio.get_running_loop()
                        future: asyncio.Future[list[dict]] = loop.create_future()
                        self._pending_responses[item.task_id] = future
                        try:
                            responses = await asyncio.wait_for(
                                future,
                                timeout=self._limits.task_timeout_seconds,
                            )
                        finally:
                            self._pending_responses.pop(item.task_id, None)

                        # Resume agent with interrupt responses. The pending
                        # approval record is no longer needed (resolved
                        # in-process), discard it.
                        from andino import approvals as _approvals
                        _approvals.discard(self._agent_dir, item.task_id)

                        input_data = responses
                        task_status.status = TaskState.running
                        task_status.interrupts = None
                        continue

                    # Normal completion
                    task_status.status = TaskState.completed
                    task_status.result = _extract_text(result)
                    structured = getattr(result, "structured_output", None)
                    if structured is not None:
                        try:
                            task_status.structured_output = structured.model_dump()
                        except Exception:
                            logger.exception("structured_output_dump_failed task_id=%s", item.task_id)

                    # Token usage + estimated cost (best-effort, never raises)
                    from andino.usage import estimate_cost, extract_usage, record_usage
                    tin, tout = extract_usage(result)
                    task_status.input_tokens = tin
                    task_status.output_tokens = tout
                    if tin or tout:
                        provider = self._config.model.provider
                        model_id = self._config.model.model_id
                        est = estimate_cost(provider, model_id, tin, tout)
                        logger.info(
                            "task_usage tokens_in=%d tokens_out=%d est_cost_usd=%s",
                            tin, tout, f"{est:.6f}" if est is not None else "n/a",
                        )
                        record_usage(
                            self._usage_file,
                            task_id=item.task_id,
                            session_id=item.session_id,
                            provider=provider,
                            model_id=model_id,
                            input_tokens=tin,
                            output_tokens=tout,
                        )
                    break

            except TimeoutError:
                logger.warning("task_timeout task_id=%s", item.task_id)
                task_status.status = TaskState.timeout
                task_status.error = f"Timed out after {self._limits.task_timeout_seconds}s"
            except Exception as exc:
                logger.exception("task_failed task_id=%s", item.task_id)
                task_status.status = TaskState.failed
                task_status.error = str(exc)[:2000]
            finally:
                lock.release()
                self._progress_callbacks.pop(item.task_id, None)
                task_status.completed_at = datetime.now(UTC).isoformat()
                event = self._completion_events.get(item.task_id)
                if event is not None:
                    event.set()
                self._queue.task_done()
                clear_task()

    def respond_to_interrupt(self, task_id: str, responses: list[dict]) -> bool:
        """Deliver human responses to a pending interrupt.

        Returns True if responses were delivered, False if no pending interrupt.
        """
        future = self._pending_responses.get(task_id)
        if future is None or future.done():
            return False
        future.set_result(responses)
        return True

    async def decide_orphaned(self, task_id: str, decision: str) -> TaskStatus | None:
        """Decide an approval whose in-memory future is gone (post-restart).

        Singular's replay pattern on files:
        1. Record the decision in the approval store.
        2. Re-submit the task (same prompt + session, fresh task id).
        3. On replay, the ToolApprovalHook sees the stored decision via
           ``lookup_decision`` and proceeds / cancels without re-asking.

        Returns the NEW task's status, or None if the approval is unknown /
        already decided / still live in-process (use respond_to_interrupt
        for live ones).
        """
        from andino import approvals as _approvals

        # Live interrupt? Then this API is the wrong door.
        if task_id in self._pending_responses:
            return None

        record = _approvals.decide(self._agent_dir, task_id, decision)
        if record is None:
            return None

        new_task_id = f"{task_id}-replay"
        logger.info(
            "approval_replay task_id=%s decision=%s new_task_id=%s",
            task_id, decision, new_task_id,
        )
        return await self.submit(
            new_task_id,
            record["prompt"],
            record.get("session_id"),
        )

    def list_pending_approvals(self) -> list[dict]:
        """Pending approvals from the file store (includes orphaned ones)."""
        from andino import approvals as _approvals

        return _approvals.load_pending(self._agent_dir)

    def on_interrupt(self, task_id: str, callback: Callable) -> None:
        """Register an async callback to invoke when a task is interrupted."""
        self._interrupt_callbacks[task_id] = callback

    def on_progress(self, task_id: str, callback: Callable) -> None:
        """Register an async callback invoked with each streaming text delta.

        The callback is awaited with the raw ``data`` string from each
        streaming event produced by ``agent.stream_async`` and is cleared
        automatically when the task completes.
        """
        self._progress_callbacks[task_id] = callback

    def get_status(self, task_id: str) -> TaskStatus | None:
        return self._tasks.get(task_id)

    def list_tasks(self) -> list[TaskStatus]:
        return list(self._tasks.values())

    def _trim_history(self) -> None:
        while len(self._tasks) > MAX_HISTORY:
            oldest_key = next(iter(self._tasks))
            oldest = self._tasks[oldest_key]
            if oldest.status in (TaskState.completed, TaskState.failed, TaskState.timeout):
                del self._tasks[oldest_key]
            else:
                break
