"""Task-scoped logging context.

Backport of Singular's trace-id discipline adapted to the single-process
runtime: every log record emitted while a task is executing carries that
task's id, so `grep task=<id>` reconstructs one task's full story across
the executor, the agent loop, tools, and channels.

Usage:
- ``configure_logging`` installs :class:`TaskIdFilter` on every handler and
  uses a format string containing ``%(task_id)s``.
- The task executor calls :func:`bind_task` / :func:`clear_task` around each
  task's execution. ContextVars propagate through ``await`` boundaries, so
  everything the task touches inherits the id without explicit plumbing.
"""

from __future__ import annotations

import logging
from contextvars import ContextVar

_CURRENT_TASK_ID: ContextVar[str | None] = ContextVar("andino_current_task_id", default=None)


def bind_task(task_id: str) -> None:
    """Attach ``task_id`` to the current async context."""
    _CURRENT_TASK_ID.set(task_id)


def clear_task() -> None:
    """Detach the task id (defensive reset at task teardown)."""
    _CURRENT_TASK_ID.set(None)


def current_task_id() -> str | None:
    return _CURRENT_TASK_ID.get()


class TaskIdFilter(logging.Filter):
    """Inject ``record.task_id`` so format strings can reference it.

    Records emitted outside any task context get ``-`` (keeps the format
    stable for service startup / channel lifecycle lines).
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.task_id = _CURRENT_TASK_ID.get() or "-"
        return True
