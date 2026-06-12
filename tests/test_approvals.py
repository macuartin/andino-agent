"""File-backed HITL approval store + replay semantics."""

from __future__ import annotations

import json

import pytest

from andino import approvals
from andino.hitl import ToolApprovalHook


@pytest.fixture
def agent_dir(tmp_path):
    return tmp_path / "agents" / "tester"


def _pending(agent_dir, task_id="t1", session_id="s1", tool="shell"):
    approvals.save_pending(
        agent_dir,
        task_id=task_id,
        session_id=session_id,
        prompt="run the thing",
        interrupts=[{
            "interrupt_id": "i1",
            "name": f"approve:{tool}",
            "reason": {"tool_name": tool, "tool_input": {"cmd": "ls"}},
        }],
    )


class TestStore:
    def test_save_and_load_pending(self, agent_dir):
        _pending(agent_dir)
        pending = approvals.load_pending(agent_dir)
        assert len(pending) == 1
        assert pending[0]["task_id"] == "t1"
        assert pending[0]["status"] == approvals.PENDING

    def test_decide_flips_status(self, agent_dir):
        _pending(agent_dir)
        record = approvals.decide(agent_dir, "t1", approvals.APPROVED)
        assert record["status"] == approvals.APPROVED
        assert record["decided_at"] is not None
        assert approvals.load_pending(agent_dir) == []  # no longer pending

    def test_decide_unknown_returns_none(self, agent_dir):
        assert approvals.decide(agent_dir, "nope", approvals.APPROVED) is None

    def test_decide_twice_is_idempotent(self, agent_dir):
        _pending(agent_dir)
        assert approvals.decide(agent_dir, "t1", approvals.APPROVED) is not None
        assert approvals.decide(agent_dir, "t1", approvals.DENIED) is None  # already decided

    def test_decide_invalid_decision_raises(self, agent_dir):
        _pending(agent_dir)
        with pytest.raises(ValueError):
            approvals.decide(agent_dir, "t1", "maybe")

    def test_discard_removes_record(self, agent_dir):
        _pending(agent_dir)
        approvals.discard(agent_dir, "t1")
        assert approvals.get(agent_dir, "t1") is None


class TestLookupConsume:
    def test_lookup_finds_decided_for_session_tool(self, agent_dir):
        _pending(agent_dir, session_id="s1", tool="shell")
        approvals.decide(agent_dir, "t1", approvals.APPROVED)
        assert approvals.lookup_decision(agent_dir, "s1", "shell") == approvals.APPROVED

    def test_lookup_wrong_session_returns_none(self, agent_dir):
        _pending(agent_dir, session_id="s1", tool="shell")
        approvals.decide(agent_dir, "t1", approvals.APPROVED)
        assert approvals.lookup_decision(agent_dir, "other", "shell") is None

    def test_lookup_pending_returns_none(self, agent_dir):
        _pending(agent_dir)
        assert approvals.lookup_decision(agent_dir, "s1", "shell") is None

    def test_consume_is_single_shot(self, agent_dir):
        _pending(agent_dir, session_id="s1", tool="shell")
        approvals.decide(agent_dir, "t1", approvals.APPROVED)
        assert approvals.lookup_decision(agent_dir, "s1", "shell") == approvals.APPROVED
        approvals.consume_decision(agent_dir, "s1", "shell")
        assert approvals.lookup_decision(agent_dir, "s1", "shell") is None


class _FakeEvent:
    """Minimal BeforeToolCallEvent stand-in."""

    def __init__(self, tool_name):
        self.tool_use = {"name": tool_name, "input": {}}
        self.cancel_tool = None
        self.interrupted = False

    def interrupt(self, name, reason=None):
        self.interrupted = True
        return "approved"  # in-process default for these tests


class TestHookReplay:
    def test_stored_approval_skips_interrupt(self, agent_dir):
        _pending(agent_dir, session_id="s1", tool="shell")
        approvals.decide(agent_dir, "t1", approvals.APPROVED)

        hook = ToolApprovalHook(
            require_approval=["shell"], agent_dir=agent_dir, session_id="s1",
        )
        event = _FakeEvent("shell")
        hook._check_approval(event)
        assert event.interrupted is False   # decision applied from store
        assert event.cancel_tool is None    # approved → tool runs

    def test_stored_denial_cancels_tool(self, agent_dir):
        _pending(agent_dir, session_id="s1", tool="shell")
        approvals.decide(agent_dir, "t1", approvals.DENIED)

        hook = ToolApprovalHook(
            require_approval=["shell"], agent_dir=agent_dir, session_id="s1",
        )
        event = _FakeEvent("shell")
        hook._check_approval(event)
        assert event.interrupted is False
        assert "denied" in (event.cancel_tool or "")

    def test_no_stored_decision_interrupts_normally(self, agent_dir):
        hook = ToolApprovalHook(
            require_approval=["shell"], agent_dir=agent_dir, session_id="s1",
        )
        event = _FakeEvent("shell")
        hook._check_approval(event)
        assert event.interrupted is True   # normal flow

    def test_stored_decision_consumed_single_shot(self, agent_dir):
        """Second gated call after a consumed decision re-interrupts."""
        _pending(agent_dir, session_id="s1", tool="shell")
        approvals.decide(agent_dir, "t1", approvals.APPROVED)

        hook = ToolApprovalHook(
            require_approval=["shell"], agent_dir=agent_dir, session_id="s1",
        )
        first = _FakeEvent("shell")
        hook._check_approval(first)
        assert first.interrupted is False

        second = _FakeEvent("shell")
        hook._check_approval(second)
        assert second.interrupted is True  # decision was consumed

    def test_ungated_tool_untouched(self, agent_dir):
        hook = ToolApprovalHook(
            require_approval=["shell"], agent_dir=agent_dir, session_id="s1",
        )
        event = _FakeEvent("calculator")
        hook._check_approval(event)
        assert event.interrupted is False
        assert event.cancel_tool is None
