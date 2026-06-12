"""Conversation forking + listing over FileSessionManager storage.

Backport of Singular's ``fork_session`` to the file layout Strands'
FileSessionManager produces::

    <storage_dir>/session_<id>/
        session.json
        agents/
            agent_<aid>/
                agent.json          # state + conversation_manager_state + _internal_state
                messages/
                    message_<n>.json

A fork copies the whole session directory under a new id, optionally
trimming messages with index > ``at_message``, rewrites the embedded
``session_id``, and resets any in-flight interrupt state so the branch
starts clean. Forks are explorations: run the same conversation forward
from message N with a different prompt, model, or agent version.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_MSG_RE = re.compile(r"^message_(\d+)\.json$")


def _session_dir(storage_dir: Path, session_id: str) -> Path:
    # FileSessionManager prefixes directories with "session_".
    name = session_id if session_id.startswith("session_") else f"session_{session_id}"
    return storage_dir / name


def _normalize_id(session_id: str) -> str:
    return session_id.removeprefix("session_")


def list_sessions(storage_dir: Path) -> list[dict[str, Any]]:
    """All sessions under ``storage_dir`` with message counts."""
    out: list[dict[str, Any]] = []
    if not storage_dir.is_dir():
        return out
    for d in sorted(storage_dir.iterdir()):
        if not d.is_dir() or not d.name.startswith("session_"):
            continue
        session_file = d / "session.json"
        meta: dict[str, Any] = {}
        if session_file.is_file():
            try:
                meta = json.loads(session_file.read_text(encoding="utf-8"))
            except ValueError:
                pass
        msg_count = sum(
            1
            for agent_dir in (d / "agents").glob("agent_*")
            for _ in (agent_dir / "messages").glob("message_*.json")
        ) if (d / "agents").is_dir() else 0
        out.append({
            "session_id": meta.get("session_id", _normalize_id(d.name)),
            "messages": msg_count,
            "updated_at": meta.get("updated_at", ""),
            "path": str(d),
        })
    return out


def fork_session(
    storage_dir: Path,
    src_id: str,
    dst_id: str,
    *,
    at_message: int | None = None,
) -> int:
    """Copy ``src_id``'s history into ``dst_id``.

    Args:
        storage_dir: FileSessionManager storage root.
        src_id: Source session id (with or without the ``session_`` prefix).
        dst_id: New session id (must not exist).
        at_message: Keep messages with index <= ``at_message``. ``None``
            copies the full history.

    Returns:
        Number of message files in the fork.

    Raises:
        ValueError: missing source / existing destination.
    """
    src_dir = _session_dir(storage_dir, src_id)
    dst_dir = _session_dir(storage_dir, dst_id)
    if not src_dir.is_dir():
        raise ValueError(f"Source session {src_id!r} not found under {storage_dir}")
    if dst_dir.exists():
        raise ValueError(f"Destination session {dst_id!r} already exists")

    shutil.copytree(src_dir, dst_dir)

    # Rewrite the embedded session id.
    session_file = dst_dir / "session.json"
    if session_file.is_file():
        try:
            meta = json.loads(session_file.read_text(encoding="utf-8"))
            meta["session_id"] = _normalize_id(dst_id)
            session_file.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        except ValueError:
            logger.warning("fork_session_meta_rewrite_failed dst=%s", dst_id)

    kept = 0
    agents_dir = dst_dir / "agents"
    if agents_dir.is_dir():
        for agent_dir in agents_dir.glob("agent_*"):
            # Trim messages beyond the fork point.
            messages_dir = agent_dir / "messages"
            if messages_dir.is_dir():
                for msg_file in messages_dir.glob("message_*.json"):
                    m = _MSG_RE.match(msg_file.name)
                    if m is None:
                        continue
                    idx = int(m.group(1))
                    if at_message is not None and idx > at_message:
                        msg_file.unlink()
                    else:
                        kept += 1

            # Reset in-flight interrupt state — the branch starts clean.
            agent_file = agent_dir / "agent.json"
            if agent_file.is_file():
                try:
                    agent_meta = json.loads(agent_file.read_text(encoding="utf-8"))
                    if agent_meta.get("_internal_state"):
                        agent_meta["_internal_state"] = {}
                        agent_file.write_text(
                            json.dumps(agent_meta, indent=2), encoding="utf-8",
                        )
                except ValueError:
                    logger.warning("fork_session_agent_meta_failed dst=%s", dst_id)

    logger.info(
        "session_forked src=%s dst=%s at_message=%s kept=%d",
        src_id, dst_id, at_message, kept,
    )
    return kept
