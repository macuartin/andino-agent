"""Human-in-the-loop approval hook for gating tool execution."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class HitlConfig(BaseModel):
    """HITL configuration from agent.yaml."""

    require_approval: list[str] = []


class ToolApprovalHook:
    """Strands HookProvider that interrupts before configured tools for human approval."""

    def __init__(self, require_approval: list[str]) -> None:
        self._tools = set(require_approval)

    def register_hooks(self, registry: Any, **kwargs: Any) -> None:
        from strands.hooks import BeforeToolCallEvent

        registry.add_callback(BeforeToolCallEvent, self._check_approval)

    def _check_approval(self, event: Any) -> None:
        tool_name = event.tool_use["name"]
        if tool_name not in self._tools:
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
