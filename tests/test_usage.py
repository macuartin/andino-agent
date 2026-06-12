"""Usage extraction, pricing, JSONL recording, and summarization."""

from __future__ import annotations

import json

from andino.usage import estimate_cost, extract_usage, record_usage, summarize


class _Metrics:
    def __init__(self, usage):
        self.accumulated_usage = usage


class _Result:
    def __init__(self, usage=None):
        if usage is not None:
            self.metrics = _Metrics(usage)


class TestExtractUsage:
    def test_dict_usage(self):
        r = _Result({"inputTokens": 1200, "outputTokens": 340})
        assert extract_usage(r) == (1200, 340)

    def test_missing_metrics_returns_zero(self):
        assert extract_usage(object()) == (0, 0)

    def test_missing_keys_default_zero(self):
        r = _Result({})
        assert extract_usage(r) == (0, 0)

    def test_none_values_default_zero(self):
        r = _Result({"inputTokens": None, "outputTokens": None})
        assert extract_usage(r) == (0, 0)


class TestEstimateCost:
    def test_known_model(self):
        # 1M in * $3 + 0.2M out * $15 = 3 + 3 = $6
        cost = estimate_cost("bedrock", "us.anthropic.claude-sonnet-4-6", 1_000_000, 200_000)
        assert cost == 6.0

    def test_unknown_model_returns_none(self):
        assert estimate_cost("bedrock", "fictional-model", 1000, 1000) is None


class TestRecordAndSummarize:
    def test_record_appends_jsonl(self, tmp_path):
        f = tmp_path / "usage.jsonl"
        record_usage(
            f, task_id="t1", session_id="s1",
            provider="bedrock", model_id="us.anthropic.claude-sonnet-4-6",
            input_tokens=1000, output_tokens=500,
        )
        record_usage(
            f, task_id="t2", session_id=None,
            provider="bedrock", model_id="us.anthropic.claude-sonnet-4-6",
            input_tokens=2000, output_tokens=800,
        )
        lines = f.read_text().splitlines()
        assert len(lines) == 2
        first = json.loads(lines[0])
        assert first["task_id"] == "t1"
        assert first["input_tokens"] == 1000
        assert first["est_cost_usd"] is not None

    def test_summarize_totals(self, tmp_path):
        f = tmp_path / "usage.jsonl"
        for i in range(3):
            record_usage(
                f, task_id=f"t{i}", session_id=None,
                provider="bedrock", model_id="us.anthropic.claude-sonnet-4-6",
                input_tokens=1000, output_tokens=100,
            )
        stats = summarize(f)
        assert stats["tasks"] == 3
        assert stats["input_tokens"] == 3000
        assert stats["output_tokens"] == 300
        assert stats["est_cost_usd"] > 0

    def test_summarize_missing_file(self, tmp_path):
        stats = summarize(tmp_path / "nope.jsonl")
        assert stats == {"tasks": 0, "input_tokens": 0, "output_tokens": 0, "est_cost_usd": 0.0}

    def test_summarize_skips_malformed_lines(self, tmp_path):
        f = tmp_path / "usage.jsonl"
        f.write_text('{"ts": "2026-01-01T00:00:00+00:00", "input_tokens": 5, "output_tokens": 5}\nnot json\n')
        stats = summarize(f)
        assert stats["tasks"] == 1

    def test_record_never_raises(self, tmp_path, monkeypatch):
        # Point at an unwritable path — must log, not raise.
        f = tmp_path / "ro" / "usage.jsonl"
        f.parent.mkdir()
        f.parent.chmod(0o444)
        try:
            record_usage(
                f, task_id="t", session_id=None,
                provider="bedrock", model_id="m", input_tokens=1, output_tokens=1,
            )  # no exception
        finally:
            f.parent.chmod(0o755)
