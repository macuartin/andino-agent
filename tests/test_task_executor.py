from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from andino.task_executor import (
    MAX_HISTORY,
    AgentPool,
    TaskExecutor,
    TaskState,
    TaskStatus,
    _extract_text,
)


class TestTaskState:
    def test_enum_values(self):
        assert TaskState.queued == "queued"
        assert TaskState.running == "running"
        assert TaskState.completed == "completed"
        assert TaskState.failed == "failed"
        assert TaskState.timeout == "timeout"


class TestTaskStatus:
    def test_minimal(self):
        ts = TaskStatus(task_id="t1", status=TaskState.queued)
        assert ts.task_id == "t1"
        assert ts.result is None
        assert ts.error is None

    def test_serialization(self):
        ts = TaskStatus(task_id="t1", status=TaskState.completed, result="done")
        data = ts.model_dump()
        assert data["task_id"] == "t1"
        assert data["status"] == "completed"
        assert data["result"] == "done"


class TestExtractText:
    def test_dict_message_with_content(self):
        result = MagicMock()
        result.message = {"content": [{"text": "Hello"}, {"text": "World"}]}
        assert _extract_text(result) == "Hello\nWorld"

    def test_dict_message_empty_content(self):
        result = MagicMock()
        result.message = {"content": []}
        assert _extract_text(result) == ""

    def test_string_message(self):
        result = MagicMock()
        result.message = "plain text"
        assert _extract_text(result) == "plain text"

    def test_no_message_attribute(self):
        assert _extract_text("raw string") == "raw string"

    def test_content_with_non_text_blocks(self):
        result = MagicMock()
        result.message = {"content": [{"image": "data"}, {"text": "only this"}]}
        assert _extract_text(result) == "only this"


class TestAgentPool:
    @patch("andino.task_executor.build_agent")
    def test_stateless_agent_in_cache(self, mock_build, sample_config):
        mock_build.return_value = MagicMock()
        pool = AgentPool(sample_config)
        assert None in pool._cache

    @patch("andino.task_executor.build_agent")
    async def test_acquire_stateless(self, mock_build, sample_config):
        mock_agent = MagicMock()
        mock_build.return_value = mock_agent
        pool = AgentPool(sample_config)

        agent, lock = await pool.acquire(None)
        assert agent is mock_agent
        lock.release()

    @patch("andino.task_executor.build_agent")
    async def test_acquire_with_session_creates_agent(self, mock_build, sample_config):
        mock_build.return_value = MagicMock()
        pool = AgentPool(sample_config)

        _agent, lock = await pool.acquire("session-1")
        assert "session-1" in pool._cache
        lock.release()
        assert mock_build.call_count == 2  # stateless + session-1

    @patch("andino.task_executor.build_agent")
    async def test_acquire_cached_session(self, mock_build, sample_config):
        mock_build.return_value = MagicMock()
        pool = AgentPool(sample_config)

        _, lock1 = await pool.acquire("s1")
        lock1.release()
        _, lock2 = await pool.acquire("s1")
        lock2.release()
        assert mock_build.call_count == 2  # stateless + s1 (only once)

    @patch("andino.task_executor.build_agent")
    async def test_lru_eviction(self, mock_build, sample_config):
        sample_config.session.max_pool_size = 2  # 2 slots including None
        mock_build.return_value = MagicMock()
        pool = AgentPool(sample_config)

        _, l1 = await pool.acquire("a")
        l1.release()
        _, l2 = await pool.acquire("b")
        l2.release()
        _, l3 = await pool.acquire("c")
        l3.release()

        # "a" should have been evicted (LRU)
        assert "a" not in pool._cache
        assert None in pool._cache  # None never evicted


class TestTaskExecutor:
    @patch("andino.task_executor.build_agent")
    async def test_submit_creates_queued_task(self, mock_build, sample_config):
        mock_build.return_value = MagicMock()
        executor = TaskExecutor(sample_config)

        status = await executor.submit("task-1", "Hello")
        assert status.status == TaskState.queued
        assert status.task_id == "task-1"
        assert status.prompt == "Hello"
        assert status.created_at is not None

    @patch("andino.task_executor.build_agent")
    async def test_get_status(self, mock_build, sample_config):
        mock_build.return_value = MagicMock()
        executor = TaskExecutor(sample_config)

        await executor.submit("task-1", "Hello")
        status = executor.get_status("task-1")
        assert status is not None
        assert status.task_id == "task-1"

    @patch("andino.task_executor.build_agent")
    async def test_get_status_not_found(self, mock_build, sample_config):
        mock_build.return_value = MagicMock()
        executor = TaskExecutor(sample_config)
        assert executor.get_status("nonexistent") is None

    @patch("andino.task_executor.build_agent")
    async def test_list_tasks(self, mock_build, sample_config):
        mock_build.return_value = MagicMock()
        executor = TaskExecutor(sample_config)

        await executor.submit("t1", "A")
        await executor.submit("t2", "B")
        tasks = executor.list_tasks()
        assert len(tasks) == 2

    @patch("andino.task_executor.build_agent")
    async def test_running_count(self, mock_build, sample_config):
        mock_build.return_value = MagicMock()
        executor = TaskExecutor(sample_config)
        assert executor.running_count == 0

    @patch("andino.task_executor.build_agent")
    async def test_queue_full_raises(self, mock_build, sample_config):
        mock_build.return_value = MagicMock()
        sample_config.limits.max_concurrent_tasks = 1  # queue size = 2
        executor = TaskExecutor(sample_config)

        await executor.submit("t1", "A")
        await executor.submit("t2", "B")
        with pytest.raises(ValueError, match="queue is full"):
            await executor.submit("t3", "C")

    @patch("andino.task_executor.build_agent")
    async def test_worker_completes_task(self, mock_build, sample_config):
        mock_agent = MagicMock()
        mock_result = MagicMock()
        mock_result.message = {"content": [{"text": "Done!"}]}
        mock_agent.invoke_async = AsyncMock(return_value=mock_result)
        mock_build.return_value = mock_agent

        executor = TaskExecutor(sample_config)
        await executor.submit("t1", "Do something")

        # Give workers time to process
        await asyncio.sleep(0.2)

        status = executor.get_status("t1")
        assert status.status == TaskState.completed
        assert status.result == "Done!"

    @patch("andino.task_executor.build_agent")
    async def test_worker_handles_error(self, mock_build, sample_config):
        mock_agent = MagicMock()
        mock_agent.invoke_async = AsyncMock(side_effect=RuntimeError("boom"))
        mock_build.return_value = mock_agent

        executor = TaskExecutor(sample_config)
        await executor.submit("t1", "Fail")

        await asyncio.sleep(0.2)

        status = executor.get_status("t1")
        assert status.status == TaskState.failed
        assert "boom" in status.error

    @patch("andino.task_executor.build_agent")
    async def test_worker_handles_timeout(self, mock_build, sample_config):
        sample_config.limits.task_timeout_seconds = 0  # instant timeout

        async def slow_invoke(prompt):
            await asyncio.sleep(10)

        mock_agent = MagicMock()
        mock_agent.invoke_async = slow_invoke
        mock_build.return_value = mock_agent

        executor = TaskExecutor(sample_config)
        await executor.submit("t1", "Slow")

        await asyncio.sleep(0.3)

        status = executor.get_status("t1")
        assert status.status == TaskState.timeout

    @patch("andino.task_executor.build_agent")
    async def test_trim_history(self, mock_build, sample_config):
        mock_build.return_value = MagicMock()
        executor = TaskExecutor(sample_config)

        # Fill beyond MAX_HISTORY with completed tasks
        for i in range(MAX_HISTORY + 5):
            tid = f"t-{i}"
            executor._tasks[tid] = TaskStatus(
                task_id=tid,
                status=TaskState.completed,
                prompt="x",
            )
        executor._trim_history()
        assert len(executor._tasks) <= MAX_HISTORY
