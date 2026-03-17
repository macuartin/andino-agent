"""Channel abstraction for connecting agents to messaging platforms."""

from __future__ import annotations

import importlib
import logging
import uuid
from abc import ABC, abstractmethod
from typing import Any

from andino.config import AgentConfig
from andino.task_executor import TaskExecutor, TaskStatus

logger = logging.getLogger(__name__)

_REGISTRY: dict[str, str] = {
    "slack": "andino.channels.slack:SlackChannel",
}


class BaseChannel(ABC):
    """Base class for all communication channels."""

    def __init__(self, name: str, raw_config: dict[str, Any], executor: TaskExecutor) -> None:
        self.name = name
        self._raw_config = raw_config
        self._executor = executor

    @abstractmethod
    async def start(self) -> None:
        """Start listening for messages from the platform."""

    @abstractmethod
    async def stop(self) -> None:
        """Gracefully shut down the channel."""

    def _format(self, text: str) -> str:
        """Convert agent output to channel-native format. Override per channel."""
        return text

    async def submit_and_wait(self, prompt: str, session_id: str | None = None) -> TaskStatus:
        """Submit a task and wait for completion."""
        task_id = str(uuid.uuid4())
        return await self._executor.submit_and_wait(task_id, prompt, session_id)


def load_channels(config: AgentConfig, executor: TaskExecutor) -> list[BaseChannel]:
    """Instantiate enabled channels from ``config.channels``."""
    channels: list[BaseChannel] = []

    for name, raw_config in config.channels.items():
        if not raw_config.get("enabled", True):
            logger.info("channel_disabled name=%s", name)
            continue

        import_path = _REGISTRY.get(name)
        if import_path is None:
            logger.warning("channel_unknown name=%s (available: %s)", name, list(_REGISTRY))
            continue

        module_path, attr = import_path.rsplit(":", 1)
        module = importlib.import_module(module_path)
        cls = getattr(module, attr)

        channel = cls(name=name, raw_config=raw_config, executor=executor)
        channels.append(channel)
        logger.info("channel_loaded name=%s type=%s", name, cls.__name__)

    return channels
