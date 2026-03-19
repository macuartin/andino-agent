"""Slack channel using Socket Mode."""

from __future__ import annotations

import logging
import re
from typing import Any

from pydantic import BaseModel

from andino.channels import BaseChannel
from andino.task_executor import TaskExecutor, TaskStatus

logger = logging.getLogger(__name__)


_CODE_BLOCK_RE = re.compile(r"```.*?\n(.*?)```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`([^`]+)`")


def _md_to_mrkdwn(text: str) -> str:
    """Convert standard markdown to Slack mrkdwn format.

    Preserves code blocks and inline code, then converts bold, italic,
    strikethrough, headings, images, and links.
    """
    # Extract code blocks and inline code to protect them from conversion
    placeholders: list[str] = []

    def _protect(match: re.Match) -> str:
        placeholders.append(match.group(0))
        return f"\x00{len(placeholders) - 1}\x00"

    text = _CODE_BLOCK_RE.sub(_protect, text)
    text = _INLINE_CODE_RE.sub(_protect, text)

    # Images: ![alt](url) → <url|alt>
    text = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", r"<\2|\1>", text)

    # Links: [text](url) → <url|text>
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"<\2|\1>", text)

    # Italic first: *text* (single, not bold **) → _text_
    # Must run before bold conversion to avoid false matches
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"_\1_", text)

    # Bold: **text** or __text__ → *text*
    text = re.sub(r"\*\*(.+?)\*\*", r"*\1*", text)
    text = re.sub(r"__(.+?)__", r"*\1*", text)

    # Strikethrough: ~~text~~ → ~text~
    text = re.sub(r"~~(.+?)~~", r"~\1~", text)

    # Headings: # Text → *Text* (bold)
    text = re.sub(r"^#{1,6}\s+(.+)$", r"*\1*", text, flags=re.MULTILINE)

    # Restore protected code
    for i, original in enumerate(placeholders):
        text = text.replace(f"\x00{i}\x00", original)

    return text


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

        @self._app.action(re.compile(r"^hitl_(approve|deny):"))
        async def handle_hitl_action(ack: Any, action: dict, say: Any, body: dict) -> None:
            await ack()

            # Check approver whitelist
            user_id = body.get("user", {}).get("id", "")
            approvers = self._executor._config.hitl.approvers
            if approvers and user_id not in approvers:
                channel_id = body.get("channel", {}).get("id", "")
                await self._app.client.chat_postEphemeral(
                    channel=channel_id,
                    user=user_id,
                    text=":no_entry: You are not authorized to approve or deny tool executions.",
                )
                return

            action_id = action["action_id"]
            # Format: hitl_approve:task_id:interrupt_id
            parts = action_id.split(":", 2)
            decision = "approved" if parts[0] == "hitl_approve" else "denied"
            task_id = parts[1]
            interrupt_id = parts[2]

            responses = [
                {"interruptResponse": {"interruptId": interrupt_id, "response": decision}}
            ]
            if not self._executor.respond_to_interrupt(task_id, responses):
                logger.warning("hitl_already_resolved task_id=%s interrupt_id=%s", task_id, interrupt_id)
                return

            # Replace buttons with resolution status via chat_update
            msg_data = body.get("message", {})
            message_ts = msg_data.get("ts")
            channel_id = body.get("channel", {}).get("id", "")
            emoji = ":white_check_mark:" if decision == "approved" else ":x:"

            # Preserve original tool info section, replace actions with resolution
            original_blocks = msg_data.get("blocks", [])
            tool_section = original_blocks[0] if original_blocks else None
            tool_text = (
                tool_section.get("text", {}).get("text", "")
                if isinstance(tool_section, dict)
                else ""
            )

            updated_blocks = [
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": tool_text or ":gear: Tool approval"},
                },
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": f"{emoji} *{decision.capitalize()}* by <@{user_id}>",
                        }
                    ],
                },
            ]

            await self._app.client.chat_update(
                channel=channel_id,
                ts=message_ts,
                blocks=updated_blocks,
                text=f"Tool {decision} by <@{user_id}>",
            )

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

        async def on_interrupt(task_status: TaskStatus) -> None:
            await self._post_approval_buttons(say, thread_ts, task_status)

        # Register Slack upload context so the slack_upload_file tool can find this thread
        workspace_dir: str | None = None
        if self._executor._config.workspace.enabled:
            from pathlib import Path as _Path

            workspace_dir = str(
                _Path(self._executor._config.workspace.base_dir).resolve() / session_id
            )
            from andino.channels.slack_upload import register_upload_context

            register_upload_context(workspace_dir, self._app.client, channel_id, thread_ts)

        # Add processing indicator (⏳ reaction on the user's message)
        event_ts = event.get("ts", "")
        try:
            await self._app.client.reactions_add(
                channel=channel_id, timestamp=event_ts, name="hourglass_flowing_sand",
            )
        except Exception:
            pass  # Don't fail if reaction fails (permissions, rate limits, etc.)

        try:
            status = await self.submit_and_wait(prompt, session_id, on_interrupt=on_interrupt)
            response_text = status.result or status.error or "No response"
        except Exception:
            logger.exception("slack_task_failed session_id=%s", session_id)
            response_text = "An error occurred while processing your request."
        finally:
            # Remove processing indicator
            try:
                await self._app.client.reactions_remove(
                    channel=channel_id, timestamp=event_ts, name="hourglass_flowing_sand",
                )
            except Exception:
                pass
            # Clear upload context
            if workspace_dir:
                from andino.channels.slack_upload import clear_upload_context

                clear_upload_context(workspace_dir)

        response_text = self._format(response_text)

        for chunk in self._chunk_text(response_text, self._config.max_message_length):
            await say(text=chunk, thread_ts=thread_ts)

    def _derive_session_id(self, event: dict) -> str:
        channel_id = event.get("channel", "")
        # Always scope by thread: use thread_ts if replying inside a thread,
        # otherwise use ts (the message itself becomes the thread root).
        thread_ts = event.get("thread_ts") or event.get("ts", "")
        return f"slack:{channel_id}:{thread_ts}"

    async def _post_approval_buttons(
        self, say: Any, thread_ts: str | None, task_status: TaskStatus
    ) -> None:
        """Post Block Kit buttons for each pending interrupt."""
        for interrupt in task_status.interrupts or []:
            reason = interrupt.get("reason", {})
            tool_name = reason.get("tool_name", "unknown") if isinstance(reason, dict) else str(reason)
            tool_input = str(reason.get("tool_input", {}) if isinstance(reason, dict) else "")[:500]

            blocks = [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            f":warning: *Tool approval required*\n\n"
                            f"*Tool:* `{tool_name}`\n"
                            f"*Input:*\n```{tool_input}```"
                        ),
                    },
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Approve"},
                            "style": "primary",
                            "action_id": f"hitl_approve:{task_status.task_id}:{interrupt['interrupt_id']}",
                        },
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Deny"},
                            "style": "danger",
                            "action_id": f"hitl_deny:{task_status.task_id}:{interrupt['interrupt_id']}",
                        },
                    ],
                },
            ]
            await say(
                blocks=blocks,
                text=f"Approval needed: {tool_name}",
                thread_ts=thread_ts,
            )

    def _format(self, text: str) -> str:
        """Convert standard markdown to Slack mrkdwn."""
        return _md_to_mrkdwn(text)

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
