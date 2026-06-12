"""Per-task token usage + estimated cost logging.

Backport of Singular's cost tracking adapted to file storage: one JSONL
line per completed task in ``~/.andino/agents/<name>/usage.jsonl``. No
aggregation tables — `andino usage <agent>` folds the file on demand.

Pricing is a static snapshot of public per-million-token rates (same 8
models Singular seeds). Estimates only — refresh when rates change.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# (provider, model_id) -> (input_usd_per_million, output_usd_per_million)
PRICING: dict[tuple[str, str], tuple[float, float]] = {
    ("bedrock", "us.anthropic.claude-sonnet-4-6"): (3.00, 15.00),
    ("bedrock", "us.anthropic.claude-haiku-4-5"): (0.80, 4.00),
    ("bedrock", "us.anthropic.claude-opus-4-7"): (15.00, 75.00),
    ("anthropic", "claude-sonnet-4-6"): (3.00, 15.00),
    ("anthropic", "claude-haiku-4-5"): (0.80, 4.00),
    ("anthropic", "claude-opus-4-8"): (15.00, 75.00),
    ("openai", "gpt-4o"): (2.50, 10.00),
    ("openai", "gpt-4o-mini"): (0.15, 0.60),
}


def extract_usage(result: Any) -> tuple[int, int]:
    """Pull (input_tokens, output_tokens) from a Strands AgentResult.

    Defensive: every access is guarded so SDK shape drift degrades to
    ``(0, 0)`` instead of breaking task completion.
    """
    metrics = getattr(result, "metrics", None)
    if metrics is None:
        return 0, 0
    usage = getattr(metrics, "accumulated_usage", None)
    if usage is None:
        return 0, 0
    if isinstance(usage, dict):
        return int(usage.get("inputTokens", 0) or 0), int(usage.get("outputTokens", 0) or 0)
    return (
        int(getattr(usage, "inputTokens", 0) or 0),
        int(getattr(usage, "outputTokens", 0) or 0),
    )


def estimate_cost(provider: str, model_id: str, input_tokens: int, output_tokens: int) -> float | None:
    """USD estimate, or None when the model has no rate card entry."""
    rate = PRICING.get((provider, model_id))
    if rate is None:
        return None
    in_rate, out_rate = rate
    return round((input_tokens / 1_000_000) * in_rate + (output_tokens / 1_000_000) * out_rate, 6)


def record_usage(
    usage_file: Path,
    *,
    task_id: str,
    session_id: str | None,
    provider: str,
    model_id: str,
    input_tokens: int,
    output_tokens: int,
) -> None:
    """Append one JSONL record. Best-effort — never raises into the worker."""
    try:
        usage_file.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "ts": datetime.now(UTC).isoformat(),
            "task_id": task_id,
            "session_id": session_id,
            "provider": provider,
            "model_id": model_id,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "est_cost_usd": estimate_cost(provider, model_id, input_tokens, output_tokens),
        }
        with usage_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        logger.exception("usage_record_failed task_id=%s", task_id)


def summarize(usage_file: Path, days: int | None = None) -> dict[str, Any]:
    """Fold the JSONL into totals (optionally only the last N days)."""
    if not usage_file.exists():
        return {"tasks": 0, "input_tokens": 0, "output_tokens": 0, "est_cost_usd": 0.0}

    cutoff = None
    if days is not None:
        from datetime import timedelta
        cutoff = datetime.now(UTC) - timedelta(days=days)

    tasks = 0
    tin = tout = 0
    cost = 0.0
    for line in usage_file.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if cutoff is not None:
            try:
                ts = datetime.fromisoformat(entry["ts"])
                if ts < cutoff:
                    continue
            except (KeyError, ValueError):
                continue
        tasks += 1
        tin += int(entry.get("input_tokens", 0) or 0)
        tout += int(entry.get("output_tokens", 0) or 0)
        cost += float(entry.get("est_cost_usd") or 0.0)

    return {
        "tasks": tasks,
        "input_tokens": tin,
        "output_tokens": tout,
        "est_cost_usd": round(cost, 4),
    }
