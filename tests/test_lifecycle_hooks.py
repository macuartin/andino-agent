from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from andino.observability.lifecycle_hooks import LifecycleHook


@pytest.fixture
def fake_registry():
    registry = MagicMock()
    registry._callbacks = {}

    def add(event_cls, callback):
        registry._callbacks[event_cls.__name__] = callback

    registry.add_callback.side_effect = add
    return registry


class TestRegisterHooks:
    def test_registers_three_events(self, fake_registry):
        hook = LifecycleHook()
        hook.register_hooks(fake_registry)
        assert "BeforeInvocationEvent" in fake_registry._callbacks
        assert "AfterInvocationEvent" in fake_registry._callbacks
        assert "MessageAddedEvent" in fake_registry._callbacks


class TestBeforeInvocation:
    def test_records_start_time(self):
        hook = LifecycleHook(log=False)
        state: dict = {}
        event = SimpleNamespace(invocation_state=state, messages=[{"role": "user"}])
        hook._handle_before(event)
        assert "_andino_invocation_start" in state
        assert state["_andino_invocation_start"] > 0

    def test_logs_message_count(self, caplog):
        hook = LifecycleHook(log=True)
        event = SimpleNamespace(invocation_state={}, messages=[{"role": "user"}, {"role": "user"}])
        with caplog.at_level("INFO", logger="andino.observability.lifecycle_hooks"):
            hook._handle_before(event)
        assert "input_messages=2" in caplog.text


class TestAfterInvocation:
    def test_computes_duration_from_state(self, caplog):
        hook = LifecycleHook(log=True)
        state: dict = {}
        before_event = SimpleNamespace(invocation_state=state, messages=[])
        hook._handle_before(before_event)
        result = SimpleNamespace(stop_reason="end_turn")
        after_event = SimpleNamespace(invocation_state=state, result=result)
        with caplog.at_level("INFO", logger="andino.observability.lifecycle_hooks"):
            hook._handle_after(after_event)
        assert "duration_ms=" in caplog.text
        assert "stop_reason=end_turn" in caplog.text

    def test_no_state_yields_minus_one(self, caplog):
        hook = LifecycleHook(log=True)
        after_event = SimpleNamespace(invocation_state={}, result=None)
        with caplog.at_level("INFO", logger="andino.observability.lifecycle_hooks"):
            hook._handle_after(after_event)
        assert "duration_ms=-1" in caplog.text

    def test_skips_when_logging_disabled(self, caplog):
        hook = LifecycleHook(log=False)
        after_event = SimpleNamespace(invocation_state={}, result=None)
        with caplog.at_level("INFO", logger="andino.observability.lifecycle_hooks"):
            hook._handle_after(after_event)
        assert caplog.text == ""


class TestMessageAdded:
    def test_invokes_callback(self):
        captured: list = []
        hook = LifecycleHook(log=False, on_message=captured.append)
        event = SimpleNamespace(message={"role": "assistant", "content": "hi"})
        hook._handle_message(event)
        assert captured == [{"role": "assistant", "content": "hi"}]

    def test_callback_exception_logged_not_raised(self, caplog):
        def boom(_msg):
            raise RuntimeError("nope")

        hook = LifecycleHook(log=False, on_message=boom)
        event = SimpleNamespace(message={"role": "assistant"})
        with caplog.at_level("ERROR", logger="andino.observability.lifecycle_hooks"):
            hook._handle_message(event)  # must not raise
        assert "on_message_callback_failed" in caplog.text

    def test_debug_log_when_enabled(self, caplog):
        hook = LifecycleHook(log=True)
        event = SimpleNamespace(message={"role": "user"})
        with caplog.at_level("DEBUG", logger="andino.observability.lifecycle_hooks"):
            hook._handle_message(event)
        assert "role=user" in caplog.text
