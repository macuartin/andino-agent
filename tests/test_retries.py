"""Retry policy — transient failures back off and retry; permanent fail fast."""

from __future__ import annotations

import httpx
import pytest

from andino.task_executor import _is_transient


class TestIsTransient:
    def test_httpx_connect_error_is_transient(self):
        assert _is_transient(httpx.ConnectError("boom"))

    def test_httpx_read_timeout_is_transient(self):
        assert _is_transient(httpx.ReadTimeout("slow"))

    def test_connection_error_is_transient(self):
        assert _is_transient(ConnectionError("reset"))

    def test_bedrock_throttling_string_match(self):
        exc = RuntimeError(
            "An error occurred (ThrottlingException) when calling ConverseStream"
        )
        assert _is_transient(exc)

    def test_value_error_not_transient(self):
        assert not _is_transient(ValueError("bad input"))

    def test_permission_error_not_transient(self):
        exc = RuntimeError("An error occurred (AccessDeniedException) ...")
        assert not _is_transient(exc)


class TestRetryLoop:
    async def test_transient_then_success_retries(self, monkeypatch):
        """Two ConnectErrors then success → result returned, 2 retries logged."""
        from andino import task_executor as te

        calls = {"n": 0}

        async def flaky_stream(agent, input_data, on_progress):
            calls["n"] += 1
            if calls["n"] < 3:
                raise httpx.ConnectError("net down")

            class _R:
                stop_reason = "end_turn"
                interrupts = []
                message = {"content": [{"text": "ok"}]}

            return _R()

        # Exercise the retry logic in isolation (mirrors the worker's loop).
        monkeypatch.setattr(te, "_consume_stream", flaky_stream)

        import asyncio
        max_retries = 2
        attempt = 0
        while True:
            try:
                result = await asyncio.wait_for(
                    te._consume_stream(None, "hi", None), timeout=30,
                )
                break
            except TimeoutError:
                raise
            except Exception as exc:
                if attempt >= max_retries or not te._is_transient(exc):
                    raise
                attempt += 1
                await asyncio.sleep(0)  # no real backoff in tests

        assert calls["n"] == 3
        assert result.stop_reason == "end_turn"

    async def test_permanent_error_fails_fast(self, monkeypatch):
        from andino import task_executor as te

        calls = {"n": 0}

        async def broken_stream(agent, input_data, on_progress):
            calls["n"] += 1
            raise ValueError("permanent")

        monkeypatch.setattr(te, "_consume_stream", broken_stream)

        import asyncio
        with pytest.raises(ValueError):
            attempt = 0
            while True:
                try:
                    await asyncio.wait_for(te._consume_stream(None, "hi", None), timeout=30)
                    break
                except Exception as exc:
                    if attempt >= 2 or not te._is_transient(exc):
                        raise
                    attempt += 1
        assert calls["n"] == 1  # no retries for permanent errors
