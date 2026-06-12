"""Session forking over the FileSessionManager directory layout."""

from __future__ import annotations

import json

import pytest

from andino.session_tools import fork_session, list_sessions


def _seed_session(storage_dir, session_id: str, n_messages: int = 5) -> None:
    d = storage_dir / f"session_{session_id}"
    (d / "agents" / "agent_default" / "messages").mkdir(parents=True)
    (d / "session.json").write_text(json.dumps({
        "session_id": session_id,
        "session_type": "AGENT",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }))
    (d / "agents" / "agent_default" / "agent.json").write_text(json.dumps({
        "agent_id": "default",
        "state": {},
        "conversation_manager_state": {"window": 40},
        "_internal_state": {"interrupt_state": {"pending": "stuff"}},
    }))
    for i in range(n_messages):
        role = "user" if i % 2 == 0 else "assistant"
        (d / "agents" / "agent_default" / "messages" / f"message_{i}.json").write_text(
            json.dumps({"message_id": i, "message": {"role": role, "content": [{"text": f"m{i}"}]}})
        )


class TestListSessions:
    def test_empty_dir(self, tmp_path):
        assert list_sessions(tmp_path) == []

    def test_lists_with_counts(self, tmp_path):
        _seed_session(tmp_path, "abc", n_messages=4)
        _seed_session(tmp_path, "xyz", n_messages=2)
        sessions = list_sessions(tmp_path)
        assert len(sessions) == 2
        by_id = {s["session_id"]: s for s in sessions}
        assert by_id["abc"]["messages"] == 4
        assert by_id["xyz"]["messages"] == 2


class TestForkSession:
    def test_full_fork(self, tmp_path):
        _seed_session(tmp_path, "src1", n_messages=5)
        kept = fork_session(tmp_path, "src1", "branch1")
        assert kept == 5
        dst = tmp_path / "session_branch1"
        assert dst.is_dir()
        meta = json.loads((dst / "session.json").read_text())
        assert meta["session_id"] == "branch1"

    def test_partial_fork_trims_messages(self, tmp_path):
        _seed_session(tmp_path, "src2", n_messages=6)
        kept = fork_session(tmp_path, "src2", "branch2", at_message=2)
        assert kept == 3  # messages 0, 1, 2
        msgs = sorted(
            (tmp_path / "session_branch2" / "agents" / "agent_default" / "messages").glob("*.json")
        )
        assert [m.name for m in msgs] == ["message_0.json", "message_1.json", "message_2.json"]

    def test_fork_resets_interrupt_state(self, tmp_path):
        _seed_session(tmp_path, "src3", n_messages=2)
        fork_session(tmp_path, "src3", "branch3")
        agent_meta = json.loads(
            (tmp_path / "session_branch3" / "agents" / "agent_default" / "agent.json").read_text()
        )
        assert agent_meta["_internal_state"] == {}
        # conversation manager state preserved
        assert agent_meta["conversation_manager_state"] == {"window": 40}

    def test_source_untouched(self, tmp_path):
        _seed_session(tmp_path, "src4", n_messages=4)
        fork_session(tmp_path, "src4", "branch4", at_message=1)
        src_msgs = list(
            (tmp_path / "session_src4" / "agents" / "agent_default" / "messages").glob("*.json")
        )
        assert len(src_msgs) == 4  # original intact

    def test_missing_source_raises(self, tmp_path):
        with pytest.raises(ValueError, match="not found"):
            fork_session(tmp_path, "ghost", "branch")

    def test_existing_destination_raises(self, tmp_path):
        _seed_session(tmp_path, "src5", n_messages=1)
        _seed_session(tmp_path, "dst5", n_messages=1)
        with pytest.raises(ValueError, match="already exists"):
            fork_session(tmp_path, "src5", "dst5")

    def test_accepts_prefixed_ids(self, tmp_path):
        _seed_session(tmp_path, "src6", n_messages=2)
        kept = fork_session(tmp_path, "session_src6", "session_branch6")
        assert kept == 2
        assert (tmp_path / "session_branch6").is_dir()
