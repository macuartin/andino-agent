"""Build a Strands AgentTool from a named local Andino agent.

This is the entrypoint for the ``andino:<name>`` tool reference syntax in
``agent.yaml``. It loads ``$ANDINO_HOME/agents/<name>/agent.yaml``, builds
an *isolated, stateless* Agent (no session manager, fresh state reset by
the SDK between invocations), and wraps it via ``Agent.as_tool`` so the
calling agent's LLM can invoke it as a regular tool.

Design decisions:

  - **Isolated**: the referenced agent is built with ``session_id=None``
    so it has no persistent conversation history. The SDK's
    ``_reset_agent_state`` clears in-memory state between calls.
  - **Own access.yaml**: each referenced agent uses its own access
    policy; HITL approvals for its tools follow its rules, not the
    caller's.
  - **Build-time cycle detection**: agent references form a static DAG.
    If ``architect`` lists ``researcher`` and ``researcher`` lists
    ``architect``, construction would recurse forever; a context-var
    call stack catches this and raises ``AgentReferenceCycleError``.
"""

from __future__ import annotations

import contextvars
import logging
from typing import Any

logger = logging.getLogger(__name__)

_call_stack: contextvars.ContextVar[tuple[str, ...]] = contextvars.ContextVar(
    "andino_agent_reference_stack", default=()
)


class AgentReferenceCycleError(RuntimeError):
    """Raised when a build-time agent reference cycle is detected."""


def build_agent_tool(name: str) -> Any:
    """Build an ``Agent.as_tool`` from ``$ANDINO_HOME/agents/<name>/agent.yaml``.

    Args:
        name: Local agent name. Resolved against ANDINO_HOME via
            :func:`andino.home.resolve_agent_dir`.

    Returns:
        A Strands tool object suitable for inclusion in another agent's
        ``tools=[...]`` list.

    Raises:
        FileNotFoundError: the referenced agent has no ``agent.yaml``.
        AgentReferenceCycleError: invoking would close a build-time cycle.
    """
    from andino.agent_builder import build_agent
    from andino.config import AgentConfig
    from andino.home import resolve_agent_dir

    stack = _call_stack.get()
    if name in stack:
        chain = " -> ".join((*stack, name))
        raise AgentReferenceCycleError(f"agent reference cycle: {chain}")

    yaml_path = resolve_agent_dir(name) / "agent.yaml"
    if not yaml_path.is_file():
        raise FileNotFoundError(
            f"Referenced agent '{name}' has no agent.yaml at {yaml_path}"
        )

    token = _call_stack.set((*stack, name))
    try:
        config = AgentConfig.from_yaml(str(yaml_path))
        agent = build_agent(config, session_id=None)
    finally:
        _call_stack.reset(token)

    description = config.description or f"Delegate to the '{name}' Andino agent."
    logger.info("agent_tool_built name=%s tools=%d", name, len(config.tools))
    return agent.as_tool(name=name, description=description)
