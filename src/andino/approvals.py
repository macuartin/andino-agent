"""File-backed HITL approval store.

Backport of Singular's persistent-approval pattern to the file-based
runtime. Pending interrupts survive process restarts:

- When the agent interrupts on a gated tool, the executor persists a
  pending approval record to
  ``$ANDINO_HOME/agents/<name>/approvals/<task_id>.json``.
- While the process lives, the existing in-memory future flow resolves
  the interrupt as before (no behavior change).
- After a restart the future is gone (the agent generator died with the
  process). Deciding an *orphaned* approval re-submits the task (same
  prompt + session); the :class:`~andino.hitl.ToolApprovalHook` consults
  :func:`lookup_decision` BEFORE interrupting, sees the recorded decision,
  and proceeds / cancels without asking again.

Decisions are single-shot: ``consume_decision`` removes the record so a
second invocation of the same tool re-interrupts (fresh approval).
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

PENDING = "pending"
APPROVED = "approved"
DENIED = "denied"


def _approvals_dir(agent_dir: Path) -> Path:
    return agent_dir / "approvals"


def _path_for(agent_dir: Path, task_id: str) -> Path:
    return _approvals_dir(agent_dir) / f"{task_id}.json"


def save_pending(
    agent_dir: Path,
    *,
    task_id: str,
    session_id: str | None,
    prompt: str,
    interrupts: list[dict[str, Any]],
) -> None:
    """Persist a pending approval record. Best-effort — never raises."""
    try:
        path = _path_for(agent_dir, task_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "task_id": task_id,
            "session_id": session_id,
            "prompt": prompt,
            "interrupts": interrupts,
            "status": PENDING,
            "created_at": datetime.now(UTC).isoformat(),
            "decided_at": None,
            "decision": None,
        }
        path.write_text(json.dumps(record, indent=2), encoding="utf-8")
        logger.info("approval_persisted task_id=%s tools=%s",
                     task_id, [i.get("name") for i in interrupts])
    except Exception:  # noqa: BLE001 — persistence must never break the interrupt flow
        logger.exception("approval_persist_failed task_id=%s", task_id)


def load_pending(agent_dir: Path) -> list[dict[str, Any]]:
    """All pending approval records for this agent (post-restart visibility)."""
    out: list[dict[str, Any]] = []
    d = _approvals_dir(agent_dir)
    if not d.is_dir():
        return out
    for p in sorted(d.glob("*.json")):
        try:
            record = json.loads(p.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        if record.get("status") == PENDING:
            out.append(record)
    return out


def get(agent_dir: Path, task_id: str) -> dict[str, Any] | None:
    p = _path_for(agent_dir, task_id)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None


def decide(agent_dir: Path, task_id: str, decision: str) -> dict[str, Any] | None:
    """Record a decision on a pending approval.

    Returns the updated record, or None if missing / already decided
    (idempotency — mirrors Singular's 409 semantics).
    """
    if decision not in (APPROVED, DENIED):
        raise ValueError(f"decision must be approved|denied, got {decision!r}")
    record = get(agent_dir, task_id)
    if record is None or record.get("status") != PENDING:
        return None
    record["status"] = decision
    record["decision"] = decision
    record["decided_at"] = datetime.now(UTC).isoformat()
    _path_for(agent_dir, task_id).write_text(json.dumps(record, indent=2), encoding="utf-8")
    logger.info("approval_decided task_id=%s decision=%s", task_id, decision)
    return record


def lookup_decision(agent_dir: Path, session_id: str | None, tool_name: str) -> str | None:
    """Find an unconsumed decision for (session, tool) — the pre-interrupt check.

    Returns ``approved`` / ``denied`` if a decided-but-unconsumed record
    matches, else None. Used by the hook on replay so the human isn't asked
    twice for the same decision.
    """
    d = _approvals_dir(agent_dir)
    if not d.is_dir():
        return None
    for p in sorted(d.glob("*.json")):
        try:
            record = json.loads(p.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        if record.get("status") not in (APPROVED, DENIED):
            continue
        if record.get("session_id") != session_id:
            continue
        for intr in record.get("interrupts", []):
            name = intr.get("reason", {}).get("tool_name") or intr.get("name", "")
            if tool_name in str(name):
                return record["status"]
    return None


def consume_decision(agent_dir: Path, session_id: str | None, tool_name: str) -> None:
    """Remove the decided record that matches (session, tool) — single-shot."""
    d = _approvals_dir(agent_dir)
    if not d.is_dir():
        return
    for p in sorted(d.glob("*.json")):
        try:
            record = json.loads(p.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        if record.get("status") not in (APPROVED, DENIED):
            continue
        if record.get("session_id") != session_id:
            continue
        for intr in record.get("interrupts", []):
            name = intr.get("reason", {}).get("tool_name") or intr.get("name", "")
            if tool_name in str(name):
                p.unlink(missing_ok=True)
                logger.info("approval_consumed task_id=%s tool=%s",
                             record.get("task_id"), tool_name)
                return


def discard(agent_dir: Path, task_id: str) -> None:
    """Remove a record outright (task completed in-process, no replay needed)."""
    _path_for(agent_dir, task_id).unlink(missing_ok=True)
