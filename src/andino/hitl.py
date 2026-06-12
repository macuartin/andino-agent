"""Human-in-the-loop approval hook for gating tool execution."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ToolApprovalHook:
    """Strands HookProvider that interrupts before configured tools for human approval.

    Uses an :class:`~andino.access.AccessEvaluator` to determine which tools
    require approval.  Falls back to a simple name-set check when constructed
    with a plain list of tool names (for backward compat / tests).

    Replay support (post-restart): when ``agent_dir`` + ``session_id`` are
    provided, the hook consults the file-backed approval store BEFORE
    interrupting. A recorded ``approved``/``denied`` decision (left by
    deciding an orphaned approval) is consumed single-shot and applied
    without asking the human again — Singular's resume pattern on files.
    """

    def __init__(
        self,
        evaluator: Any = None,
        *,
        require_approval: list[str] | None = None,
        agent_dir: Path | None = None,
        session_id: str | None = None,
    ) -> None:
        if evaluator is not None:
            self._evaluator = evaluator
            self._tools: set[str] | None = None
        else:
            self._evaluator = None
            self._tools = set(require_approval or [])
        self._agent_dir = agent_dir
        self._session_id = session_id

    def register_hooks(self, registry: Any, **kwargs: Any) -> None:
        from strands.hooks import BeforeToolCallEvent

        registry.add_callback(BeforeToolCallEvent, self._check_approval)

    def _needs_approval(self, tool_name: str) -> bool:
        if self._evaluator is not None:
            return self._evaluator.needs_approval(tool_name)
        return tool_name in (self._tools or set())

    def _prior_decision(self, tool_name: str) -> str | None:
        """Check the file store for an unconsumed decision (replay path)."""
        if self._agent_dir is None:
            return None
        from andino import approvals

        decision = approvals.lookup_decision(self._agent_dir, self._session_id, tool_name)
        if decision is not None:
            approvals.consume_decision(self._agent_dir, self._session_id, tool_name)
        return decision

    def _check_approval(self, event: Any) -> None:
        tool_name = event.tool_use["name"]
        if not self._needs_approval(tool_name):
            return

        # Replay: a decision recorded while this task was orphaned (process
        # restart) applies directly — don't ask the human twice.
        prior = self._prior_decision(tool_name)
        if prior == "approved":
            logger.info("tool_approved_from_store tool=%s", tool_name)
            return
        if prior == "denied":
            event.cancel_tool = f"Tool '{tool_name}' denied by stored decision"
            logger.info("tool_denied_from_store tool=%s", tool_name)
            return

        reason = {
            "tool_name": tool_name,
            "tool_input": event.tool_use.get("input", {}),
        }
        response = event.interrupt(f"approve:{tool_name}", reason=reason)

        if response != "approved":
            event.cancel_tool = f"Tool '{tool_name}' denied: {response}"
            logger.info("tool_denied tool=%s response=%s", tool_name, response)
        else:
            logger.info("tool_approved tool=%s", tool_name)
