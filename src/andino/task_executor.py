from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel

from andino.agent_builder import build_agent
from andino.config import AgentConfig

logger = logging.getLogger(__name__)

MAX_HISTORY = 100


class TaskState(str, Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"
    timeout = "timeout"


class TaskStatus(BaseModel):
    task_id: str
    status: TaskState
    prompt: str = ""
    session_id: str | None = None
    result: str | None = None
    error: str | None = None
    created_at: str | None = None
    started_at: str | None = None
    completed_at: str | None = None


class _TaskItem:
    """Internal queue item."""

    __slots__ = ("task_id", "prompt", "session_id")

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


def _extract_text(result: object) -> str:
    """Extract text output from an AgentResult."""
    if hasattr(result, "message"):
        msg = result.message
        if isinstance(msg, dict):
            content = msg.get("content", [])
            texts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("text")]
            return "\n".join(texts)
        return str(msg)
    return str(result)


class TaskExecutor:
    """Queue-based task executor using invoke_async."""

    def __init__(self, config: AgentConfig) -> None:
        self._config = config
        self._limits = config.limits
        self._pool = AgentPool(config)
        max_queued = config.limits.max_concurrent_tasks * 2
        self._queue: asyncio.Queue[_TaskItem] = asyncio.Queue(maxsize=max_queued)
        self._tasks: OrderedDict[str, TaskStatus] = OrderedDict()
        self._workers: list[asyncio.Task] = []
        self._started = False

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

        now = datetime.now(timezone.utc).isoformat()
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

    async def _worker(self, worker_id: int) -> None:
        """Worker coroutine that consumes tasks from the queue."""
        logger.info("worker_started id=%d", worker_id)
        while True:
            item = await self._queue.get()
            task_status = self._tasks.get(item.task_id)
            if task_status is None:
                self._queue.task_done()
                continue

            task_status.status = TaskState.running
            task_status.started_at = datetime.now(timezone.utc).isoformat()

            agent, lock = await self._pool.acquire(item.session_id)
            try:
                result = await asyncio.wait_for(
                    agent.invoke_async(item.prompt),
                    timeout=self._limits.task_timeout_seconds,
                )
                task_status.status = TaskState.completed
                task_status.result = _extract_text(result)
            except asyncio.TimeoutError:
                logger.warning("task_timeout task_id=%s", item.task_id)
                task_status.status = TaskState.timeout
                task_status.error = f"Timed out after {self._limits.task_timeout_seconds}s"
            except Exception as exc:
                logger.exception("task_failed task_id=%s", item.task_id)
                task_status.status = TaskState.failed
                task_status.error = str(exc)[:2000]
            finally:
                lock.release()
                task_status.completed_at = datetime.now(timezone.utc).isoformat()
                self._queue.task_done()

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
