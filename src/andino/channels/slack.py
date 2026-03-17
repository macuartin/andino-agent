"""Slack channel using Socket Mode."""

from __future__ import annotations

import logging
import re
from typing import Any

from pydantic import BaseModel

from andino.channels import BaseChannel
from andino.task_executor import TaskExecutor

logger = logging.getLogger(__name__)


class SlackConfig(BaseModel):
    """Validated Slack channel configuration."""

    enabled: bool = True
    mode: str = "socket"
    app_token: str
    bot_token: str
    require_mention: bool = True
    allowed_channels: list[str] = []
    max_message_length: int = 3900


class SlackChannel(BaseChannel):
    """Slack Socket Mode channel."""

    def __init__(self, name: str, raw_config: dict[str, Any], executor: TaskExecutor) -> None:
        super().__init__(name, raw_config, executor)
        self._config = SlackConfig.model_validate(raw_config)
        self._app: Any = None
        self._handler: Any = None
        self._bot_user_id: str | None = None

    async def start(self) -> None:
        from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
        from slack_bolt.async_app import AsyncApp

        self._app = AsyncApp(token=self._config.bot_token)
        self._register_handlers()

        # Fetch bot user ID to filter self-messages and strip mentions
        try:
            auth = await self._app.client.auth_test()
            self._bot_user_id = auth.get("user_id")
            logger.info("slack_connected bot_user_id=%s", self._bot_user_id)
        except Exception:
            logger.warning("slack_auth_test_failed — bot self-filtering may not work")

        self._handler = AsyncSocketModeHandler(self._app, self._config.app_token)
        await self._handler.start_async()

    async def stop(self) -> None:
        if self._handler is not None:
            await self._handler.close_async()

    def _register_handlers(self) -> None:
        @self._app.event("app_mention")
        async def handle_mention(event: dict, say: Any) -> None:
            await self._handle_event(event, say)

        @self._app.event("message")
        async def handle_message(event: dict, say: Any) -> None:
            # In channels with require_mention, ignore non-mention messages
            channel_type = event.get("channel_type", "")
            if channel_type != "im" and self._config.require_mention:
                return
            await self._handle_event(event, say)

    async def _handle_event(self, event: dict, say: Any) -> None:
        # Skip bot messages (avoid infinite loops)
        if event.get("bot_id"):
            return
        if self._bot_user_id and event.get("user") == self._bot_user_id:
            return

        # Check allowed channels
        channel_id = event.get("channel", "")
        if self._config.allowed_channels and channel_id not in self._config.allowed_channels:
            return

        prompt = self._extract_prompt(event)
        if not prompt:
            return

        session_id = self._derive_session_id(event)
        thread_ts = event.get("thread_ts") or event.get("ts")

        logger.info("slack_task session_id=%s channel=%s", session_id, channel_id)

        try:
            status = await self.submit_and_wait(prompt, session_id)
            response_text = status.result or status.error or "No response"
        except Exception:
            logger.exception("slack_task_failed session_id=%s", session_id)
            response_text = "An error occurred while processing your request."

        for chunk in self._chunk_text(response_text, self._config.max_message_length):
            await say(text=chunk, thread_ts=thread_ts)

    def _derive_session_id(self, event: dict) -> str:
        channel_type = event.get("channel_type", "")
        channel_id = event.get("channel", "")
        user_id = event.get("user", "")
        thread_ts = event.get("thread_ts")

        if channel_type == "im":
            return f"slack:dm:{user_id}"

        session = f"slack:channel:{channel_id}"
        if thread_ts:
            session += f":thread:{thread_ts}"
        return session

    def _extract_prompt(self, event: dict) -> str:
        text = event.get("text", "")
        if self._bot_user_id:
            text = re.sub(rf"<@{re.escape(self._bot_user_id)}>", "", text)
        return text.strip()

    @staticmethod
    def _chunk_text(text: str, max_len: int) -> list[str]:
        if len(text) <= max_len:
            return [text]

        chunks: list[str] = []
        while text:
            if len(text) <= max_len:
                chunks.append(text)
                break
            # Try to split at last newline within limit
            split_at = text.rfind("\n", 0, max_len)
            if split_at <= 0:
                split_at = max_len
            chunks.append(text[:split_at])
            text = text[split_at:].lstrip("\n")
        return chunks
