"""Slack file upload tool with context registry.

The SlackChannel registers upload context (client, channel_id, thread_ts)
before each task invocation.  The ``slack_upload_file`` tool looks up that
context at call time so it can upload files to the correct Slack thread.

Usage in ``agent.yaml``::

    tools:
      - andino.channels.slack_upload:slack_upload_file
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from strands import tool

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Context registry — module-level singleton
# ---------------------------------------------------------------------------

_MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB

_contexts: dict[str, dict[str, Any]] = {}  # workspace_dir → {client, channel_id, thread_ts}


def register_upload_context(
    workspace_dir: str,
    client: Any,
    channel_id: str,
    thread_ts: str,
) -> None:
    """Register Slack context for the given workspace directory.

    Called by :class:`SlackChannel` before each task invocation so that the
    ``slack_upload_file`` tool can find the correct thread to upload into.
    """
    _contexts[workspace_dir] = {
        "client": client,
        "channel_id": channel_id,
        "thread_ts": thread_ts,
    }


def clear_upload_context(workspace_dir: str) -> None:
    """Remove the Slack context for the given workspace directory."""
    _contexts.pop(workspace_dir, None)


def _find_context(file_path: str) -> tuple[dict[str, Any] | None, str | None]:
    """Find the upload context whose workspace_dir contains *file_path*.

    Returns ``(context_dict, workspace_dir)`` or ``(None, None)``.
    """
    for ws_dir, ctx in _contexts.items():
        if file_path.startswith(ws_dir):
            return ctx, ws_dir
    return None, None


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------


@tool
async def slack_upload_file(file_path: str, comment: str = "") -> dict:
    """Upload a file from the workspace to the current Slack thread.

    Use this tool after creating a file (CSV, PDF, image, etc.) to share it
    with the user in the Slack conversation.

    The file_path can be an absolute path within your workspace directory,
    or a path relative to the workspace root.

    Args:
        file_path: Path to the file to upload (absolute within workspace, or relative).
        comment: Optional comment to attach to the file upload.

    Returns:
        A dict indicating success or failure.
    """
    resolved = Path(file_path)

    # Try to find context by absolute path first
    context, _ws_dir = _find_context(str(resolved))

    # If not found and path is relative, try resolving against each known workspace
    if context is None and not resolved.is_absolute():
        for ws_dir_candidate in _contexts:
            candidate = Path(ws_dir_candidate) / file_path
            if candidate.is_file():
                resolved = candidate
                context = _contexts[ws_dir_candidate]
                break

    if context is None:
        return {
            "status": "error",
            "content": [{"text": (
                f"No Slack upload context found for '{file_path}'. "
                "Ensure workspace is enabled and the agent is running via Slack channel."
            )}],
        }

    if not resolved.is_file():
        return {
            "status": "error",
            "content": [{"text": f"File not found: {file_path}"}],
        }

    # Size check
    try:
        size = resolved.stat().st_size
    except OSError as exc:
        return {
            "status": "error",
            "content": [{"text": f"Cannot read file: {exc}"}],
        }

    if size == 0:
        return {
            "status": "error",
            "content": [{"text": f"File is empty: {file_path}"}],
        }

    if size > _MAX_FILE_SIZE_BYTES:
        return {
            "status": "error",
            "content": [{"text": (
                f"File too large: {size / (1024 * 1024):.1f} MB "
                f"(max {_MAX_FILE_SIZE_BYTES // (1024 * 1024)} MB)"
            )}],
        }

    try:
        await context["client"].files_upload_v2(
            file=str(resolved),
            filename=resolved.name,
            channel=context["channel_id"],
            thread_ts=context["thread_ts"],
            title=resolved.name,
            initial_comment=comment or None,
        )
    except Exception:
        logger.exception("slack_file_upload_failed path=%s", resolved)
        return {
            "status": "error",
            "content": [{"text": f"Failed to upload '{resolved.name}' to Slack."}],
        }

    logger.info(
        "slack_file_uploaded path=%s channel=%s",
        resolved, context["channel_id"],
    )
    return {
        "status": "success",
        "content": [{"text": f"File '{resolved.name}' uploaded to Slack thread."}],
    }
