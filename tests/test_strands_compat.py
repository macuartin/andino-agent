"""Smoke tests — Strands SDK surface that andino-agent depends on.

The pin is rolling (``strands-agents>=1.34,<2``), so a minor release can
change APIs underneath us. These tests fail loudly if any of the surfaces
the runtime touches drifts. They import + type-check only — no LLM, no DB.

Backported pattern from singular-runtime's test_strands_compat.py, adapted
to this runtime's async/stream surface.
"""

from __future__ import annotations

import inspect


def test_strands_agents_major_version():
    import strands

    version = getattr(strands, "__version__", None)
    if version is None:
        from importlib.metadata import version as md_version

        version = md_version("strands-agents")
    major = int(version.split(".")[0])
    assert major == 1, f"strands-agents major changed: {version}"


def test_agent_stream_async_surface():
    """The executor consumes ``Agent.stream_async`` — must exist and be async."""
    from strands import Agent

    assert hasattr(Agent, "stream_async"), "Agent.stream_async disappeared"
    assert inspect.isasyncgenfunction(Agent.stream_async) or inspect.iscoroutinefunction(
        Agent.stream_async
    ), "Agent.stream_async is no longer async"


def test_file_session_manager_signature():
    """agent_builder constructs FileSessionManager(session_id=, storage_dir=)."""
    from strands.session import FileSessionManager

    params = inspect.signature(FileSessionManager.__init__).parameters
    assert "session_id" in params
    assert "storage_dir" in params


def test_before_tool_call_event_interrupt_surface():
    """hitl.py relies on BeforeToolCallEvent.interrupt() + .cancel_tool."""
    from strands.hooks import BeforeToolCallEvent

    assert hasattr(BeforeToolCallEvent, "interrupt"), (
        "BeforeToolCallEvent.interrupt() gone — HITL flow must be revisited"
    )
    # cancel_tool is a settable attribute on instances; verify it's part of
    # the event's contract (annotation or property).
    annotations = getattr(BeforeToolCallEvent, "__annotations__", {})
    has_cancel = "cancel_tool" in annotations or hasattr(BeforeToolCallEvent, "cancel_tool")
    assert has_cancel, "BeforeToolCallEvent.cancel_tool gone"


def test_agent_result_surface():
    """task_executor reads stop_reason / interrupts / structured_output / metrics."""
    from strands.agent.agent_result import AgentResult

    annotations = getattr(AgentResult, "__annotations__", {})
    for field in ("stop_reason", "metrics"):
        assert field in annotations or hasattr(AgentResult, field), (
            f"AgentResult.{field} gone — executor must be revisited"
        )


def test_skills_plugin_importable():
    """agent_builder loads AgentSkills from the vended plugins namespace."""
    from strands.vended_plugins.skills import AgentSkills  # noqa: F401


def test_tool_decorator_produces_tool_name():
    """tool_loader expects @tool-decorated callables to expose tool metadata."""
    from strands import tool

    @tool
    def _probe(x: str) -> dict:
        """Probe tool."""
        return {"status": "success", "content": [{"text": x}]}

    # Strands attaches metadata the loader / SDK relies on. The exact attr is
    # `tool_name` (1.x); accept either the attr or a spec object.
    assert hasattr(_probe, "tool_name") or hasattr(_probe, "TOOL_SPEC") or hasattr(_probe, "tool_spec"), (
        "@tool no longer attaches discoverable metadata — tool_loader must be revisited"
    )
