from __future__ import annotations

import asyncio
import logging
import os

import uvicorn

from andino.channels import load_channels
from andino.config import AgentConfig
from andino.server import create_app
from andino.task_executor import TaskExecutor

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
        """Start the agent HTTP server and any configured channels."""
        # Ensure non-interactive mode for Strands tools
        os.environ.setdefault("BYPASS_TOOL_CONSENT", "true")
        os.environ.setdefault("STRANDS_NON_INTERACTIVE", "true")
        os.environ.setdefault("GIT_PAGER", "")
        os.environ.setdefault("PAGER", "")
        os.environ.setdefault("GIT_TERMINAL_PROMPT", "0")

        logger.info(
            "starting agent=%s port=%d provider=%s model=%s",
            self.config.name,
            self.config.server.port,
            self.config.model.provider,
            self.config.model.model_id,
        )

        asyncio.run(self._run_async())

    async def _run_async(self) -> None:
        executor = TaskExecutor(self.config)
        app = create_app(self.config, executor=executor)
        channels = load_channels(self.config, executor)

        uv_config = uvicorn.Config(
            app,
            host=self.config.server.host,
            port=self.config.server.port,
            log_level="info",
        )
        server = uvicorn.Server(uv_config)

        coros: list[asyncio.Task] = [server.serve()]
        for ch in channels:
            coros.append(ch.start())
            logger.info("channel_starting name=%s", ch.name)

        try:
            await asyncio.gather(*coros)
        finally:
            for ch in channels:
                await ch.stop()
