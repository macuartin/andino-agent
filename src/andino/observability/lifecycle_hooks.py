"""Agent lifecycle hooks for logging and external subscribers.

Wraps Strands ``BeforeInvocationEvent`` / ``AfterInvocationEvent`` /
``MessageAddedEvent`` so andino can:

  - Emit structured logs for every agent turn (duration, message count).
  - Notify channels (Slack, etc.) when the agent appends a message,
    enabling progressive UI updates without exposing the SDK directly.

Tracking state lives on ``event.invocation_state`` (provided by the SDK
on each event), keeping it isolated per-invocation and concurrency-safe.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

_START_KEY = "_andino_invocation_start"


class LifecycleHook:
    """Strands ``HookProvider`` for invocation- and message-level events.

    Parameters
    ----------
    log:
        Emit ``logger.info`` / ``logger.debug`` lines for each event.
    on_message:
        Optional callback invoked with each ``Message`` dict added to the
        conversation. Used by channels to mirror partial assistant
        messages back to the user.
    """

    def __init__(
        self,
        *,
        log: bool = True,
        on_message: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self._log = log
        self._on_message = on_message

    def register_hooks(self, registry: Any, **_: Any) -> None:
        from strands.hooks import (
            AfterInvocationEvent,
            BeforeInvocationEvent,
            MessageAddedEvent,
        )

        registry.add_callback(BeforeInvocationEvent, self._handle_before)
        registry.add_callback(AfterInvocationEvent, self._handle_after)
        registry.add_callback(MessageAddedEvent, self._handle_message)

    def _handle_before(self, event: Any) -> None:
        event.invocation_state[_START_KEY] = time.monotonic()
        if self._log:
            messages = getattr(event, "messages", None) or []
            logger.info("invocation_started input_messages=%d", len(messages))

    def _handle_after(self, event: Any) -> None:
        if not self._log:
            return
        started = event.invocation_state.get(_START_KEY)
        duration_ms = int((time.monotonic() - started) * 1000) if started else -1
        stop_reason = getattr(getattr(event, "result", None), "stop_reason", None)
        logger.info(
            "invocation_completed duration_ms=%d stop_reason=%s",
            duration_ms,
            stop_reason,
        )

    def _handle_message(self, event: Any) -> None:
        message = event.message
        if self._log:
            role = message.get("role") if isinstance(message, dict) else None
            logger.debug("message_added role=%s", role)
        if self._on_message is not None:
            try:
                self._on_message(message)
            except Exception:
                logger.exception("on_message_callback_failed")
