from __future__ import annotations

import asyncio
import logging
import os
import signal

import uvicorn

from andino.channels import load_channels
from andino.config import AgentConfig
from andino.server import create_app
from andino.task_executor import TaskExecutor

logger = logging.getLogger(__name__)


def configure_logging(level: str = "info", log_file: str | None = None) -> None:
    """Configure the root logger with console and optional file output."""
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_file:
        from logging.handlers import RotatingFileHandler

        handlers.append(RotatingFileHandler(log_file, maxBytes=50_000_000, backupCount=3))

    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=handlers,
        force=True,
    )


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

        # Register signal handlers for graceful shutdown
        loop = asyncio.get_running_loop()
        shutdown_event = asyncio.Event()

        def _handle_signal(sig: int) -> None:
            logger.info("signal_received sig=%s, shutting down", sig)
            shutdown_event.set()

        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, _handle_signal, sig)

        # Start server and channels as concurrent tasks
        tasks = [asyncio.create_task(server.serve())]
        for ch in channels:
            tasks.append(asyncio.create_task(ch.start()))
            logger.info("channel_starting name=%s", ch.name)

        shutdown_task = asyncio.create_task(shutdown_event.wait())

        # Wait until any task completes or shutdown signal received
        _done, pending = await asyncio.wait(
            [*tasks, shutdown_task], return_when=asyncio.FIRST_COMPLETED
        )

        # Cancel remaining tasks
        for t in pending:
            t.cancel()
        await asyncio.gather(*pending, return_exceptions=True)

        # Clean up channels
        for ch in channels:
            await ch.stop()
