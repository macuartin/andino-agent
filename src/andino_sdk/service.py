from __future__ import annotations

import logging
import os

import uvicorn

from andino_sdk.config import AgentConfig
from andino_sdk.server import create_app

logger = logging.getLogger(__name__)


class AgentService:
    """Top-level entry point for running a standalone Andino agent."""

    def __init__(self, config: AgentConfig) -> None:
        self.config = config

    @classmethod
    def from_yaml(cls, path: str) -> AgentService:
        config = AgentConfig.from_yaml(path)
        return cls(config)

    def run(self) -> None:
        """Start the agent HTTP server."""
        # Ensure non-interactive mode for Strands tools
        os.environ.setdefault("BYPASS_TOOL_CONSENT", "true")
        os.environ.setdefault("STRANDS_NON_INTERACTIVE", "true")
        os.environ.setdefault("GIT_PAGER", "")
        os.environ.setdefault("PAGER", "")
        os.environ.setdefault("GIT_TERMINAL_PROMPT", "0")

        app = create_app(self.config)

        logger.info(
            "starting agent=%s port=%d provider=%s model=%s",
            self.config.name,
            self.config.server.port,
            self.config.model.provider,
            self.config.model.model_id,
        )

        uvicorn.run(
            app,
            host=self.config.server.host,
            port=self.config.server.port,
            log_level="info",
        )
