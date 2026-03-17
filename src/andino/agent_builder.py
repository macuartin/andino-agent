from __future__ import annotations

import logging
from pathlib import Path

from strands import Agent
from strands.agent.conversation_manager import SlidingWindowConversationManager

from andino.config import AgentConfig
from andino.mcp_loader import load_mcp_servers
from andino.model_registry import build_model
from andino.tool_loader import load_tools

logger = logging.getLogger(__name__)


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
    )

    tools = _build_tools(config)

    kwargs: dict = dict(
        model=model,
        tools=tools or None,
        system_prompt=config.system_prompt or None,
        conversation_manager=SlidingWindowConversationManager(),
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
