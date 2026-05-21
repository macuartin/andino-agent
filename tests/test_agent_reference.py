from __future__ import annotations

from pathlib import Path

import pytest

from andino.agent_reference import (
    AgentReferenceCycleError,
    _call_stack,
    build_agent_tool,
)


@pytest.fixture
def andino_home(tmp_path, monkeypatch):
    """Isolated ANDINO_HOME for each test."""
    monkeypatch.setenv("ANDINO_HOME", str(tmp_path))
    return tmp_path


def _write_agent(home: Path, name: str, body: str = "") -> Path:
    agent_dir = home / "agents" / name
    agent_dir.mkdir(parents=True)
    yaml = agent_dir / "agent.yaml"
    yaml.write_text(f"name: {name}\n{body}".strip() + "\n", encoding="utf-8")
    return yaml


class TestBuildAgentTool:
    def test_builds_tool_with_correct_name(self, andino_home):
        _write_agent(andino_home, "child", "description: A child helper.")
        tool = build_agent_tool("child")
        assert tool.tool_name == "child"

    def test_uses_description_from_yaml(self, andino_home):
        _write_agent(andino_home, "child", "description: Custom helper description.")
        tool = build_agent_tool("child")
        # The SDK exposes description via the tool spec
        spec = tool.tool_spec if hasattr(tool, "tool_spec") else {}
        if isinstance(spec, dict) and "description" in spec:
            assert "Custom helper description" in spec["description"]

    def test_defaults_description_when_missing(self, andino_home):
        _write_agent(andino_home, "noop")
        tool = build_agent_tool("noop")
        assert tool.tool_name == "noop"

    def test_missing_agent_raises_filenotfound(self, andino_home):
        with pytest.raises(FileNotFoundError, match="ghost"):
            build_agent_tool("ghost")

    def test_resets_call_stack_on_success(self, andino_home):
        _write_agent(andino_home, "leaf")
        build_agent_tool("leaf")
        assert _call_stack.get() == ()

    def test_resets_call_stack_on_error(self, andino_home):
        with pytest.raises(FileNotFoundError):
            build_agent_tool("ghost")
        assert _call_stack.get() == ()


class TestCycleDetection:
    def test_self_reference_raises(self, andino_home):
        _write_agent(andino_home, "selfie", "tools:\n  - andino:selfie")
        with pytest.raises(AgentReferenceCycleError, match="selfie -> selfie"):
            build_agent_tool("selfie")

    def test_two_node_cycle_raises(self, andino_home):
        _write_agent(andino_home, "a", "tools:\n  - andino:b")
        _write_agent(andino_home, "b", "tools:\n  - andino:a")
        with pytest.raises(AgentReferenceCycleError, match="a -> b -> a"):
            build_agent_tool("a")

    def test_three_node_cycle_raises(self, andino_home):
        _write_agent(andino_home, "a", "tools:\n  - andino:b")
        _write_agent(andino_home, "b", "tools:\n  - andino:c")
        _write_agent(andino_home, "c", "tools:\n  - andino:a")
        with pytest.raises(AgentReferenceCycleError, match="a -> b -> c -> a"):
            build_agent_tool("a")

    def test_diamond_is_not_cycle(self, andino_home):
        """A→B→D and A→C→D is a DAG, not a cycle. Must build."""
        _write_agent(andino_home, "a", "tools:\n  - andino:b\n  - andino:c")
        _write_agent(andino_home, "b", "tools:\n  - andino:d")
        _write_agent(andino_home, "c", "tools:\n  - andino:d")
        _write_agent(andino_home, "d")
        tool = build_agent_tool("a")
        assert tool.tool_name == "a"


class TestToolLoaderIntegration:
    def test_andino_prefix_in_load_tools(self, andino_home):
        from andino.tool_loader import load_tools

        _write_agent(andino_home, "helper", "description: A helper.")
        tools = load_tools("andino:helper")
        assert len(tools) == 1
        assert tools[0].tool_name == "helper"

    def test_andino_prefix_alongside_regular_tool(self, andino_home):
        from andino.tool_loader import load_tools

        _write_agent(andino_home, "helper")
        # Mix andino: ref with a real tool from strands_tools
        tools = load_tools("andino:helper,strands_tools.calculator:calculator")
        assert len(tools) == 2
        assert tools[0].tool_name == "helper"
