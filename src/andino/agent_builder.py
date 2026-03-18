from __future__ import annotations

import logging
from pathlib import Path

from strands import Agent

from andino.config import AgentConfig, ConversationConfig
from andino.mcp_loader import load_mcp_servers
from andino.model_registry import build_model
from andino.tool_loader import load_tools

logger = logging.getLogger(__name__)


def _build_conversation_manager(config: ConversationConfig):
    """Build a Strands ConversationManager from config."""
    name = config.manager.strip().lower()

    if name == "null":
        from strands.agent.conversation_manager import NullConversationManager

        return NullConversationManager()

    if name == "summarizing":
        from strands.agent.conversation_manager import SummarizingConversationManager

        return SummarizingConversationManager(
            summary_ratio=config.summary_ratio,
            preserve_recent_messages=config.preserve_recent_messages,
        )

    # Default: sliding_window
    from strands.agent.conversation_manager import SlidingWindowConversationManager

    return SlidingWindowConversationManager(
        window_size=config.window_size,
        should_truncate_results=config.should_truncate_results,
        per_turn=config.per_turn,
    )


def _build_tools(config: AgentConfig) -> list:
    tools = load_tools(",".join(config.tools)) if config.tools else []
    mcp_clients = load_mcp_servers(config.mcp_servers)
    tools.extend(mcp_clients)
    return tools


def build_agent(config: AgentConfig, session_id: str | None = None) -> Agent:
    """Build a Strands Agent from an AgentConfig.

    If *session_id* is provided, a ``FileSessionManager`` is attached so
    conversation state persists across invocations for that session.
    """
    model = build_model(
        config.model.provider,
        config.model.model_id,
        max_tokens=config.model.max_tokens,
        extras=config.model.extras or None,
    )

    tools = _build_tools(config)

    hooks: list = []
    if config.hitl.require_approval:
        from andino.hitl import ToolApprovalHook

        hooks.append(ToolApprovalHook(config.hitl.require_approval))

    # Build system_prompt — optionally enriched with workspace path
    system_prompt = config.system_prompt or None
    workspace_dir: Path | None = None

    if config.workspace.enabled and session_id:
        workspace_dir = Path(config.workspace.base_dir).resolve() / session_id
        workspace_dir.mkdir(parents=True, exist_ok=True)
        workspace_note = (
            "\n\n## Workspace\n"
            f"Your workspace directory is: {workspace_dir}\n"
            "Use this directory for all file operations, downloads, and artifacts.\n"
            "When using the shell tool, set work_dir to this path.\n"
            "When writing files, use absolute paths within this directory."
        )
        system_prompt = (system_prompt or "") + workspace_note
        logger.info("workspace_created session_id=%s dir=%s", session_id, workspace_dir)

    kwargs: dict = dict(
        model=model,
        tools=tools or None,
        system_prompt=system_prompt,
        conversation_manager=_build_conversation_manager(config.conversation),
        hooks=hooks or None,
    )

    if session_id is not None:
        try:
            from strands.session import FileSessionManager

            storage_dir = Path(config.session.storage_dir).resolve()
            storage_dir.mkdir(parents=True, exist_ok=True)
            kwargs["session_manager"] = FileSessionManager(
                session_id=session_id,
                storage_dir=str(storage_dir),
            )
            logger.info("session_manager attached session_id=%s dir=%s", session_id, storage_dir)
        except ImportError:
            logger.warning("FileSessionManager not available in this strands version, running stateless")

    agent = Agent(**kwargs)

    logger.info(
        "agent_built name=%s provider=%s model=%s tools=%d session=%s",
        config.name,
        config.model.provider,
        config.model.model_id,
        len(tools),
        session_id or "stateless",
    )
    return agent
