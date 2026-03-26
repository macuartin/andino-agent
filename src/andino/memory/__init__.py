"""Andino memory system — pluggable long-term memory for agents."""

from __future__ import annotations

import logging
from typing import Any

from andino.home import resolve_data_path
from andino.memory.provider import MemoryEntry, MemoryProvider
from andino.memory.tool import create_memory_tool

logger = logging.getLogger(__name__)

__all__ = ["MemoryEntry", "MemoryProvider", "build_memory_provider", "create_memory_tool"]


def build_memory_provider(agent_name: str, provider: str, options: dict[str, Any]) -> MemoryProvider:
    """Build a memory provider from config.

    Args:
        agent_name: Agent name (used as subdirectory).
        provider: Provider name (e.g. "lancedb").
        options: Provider-specific options from agent.yaml.
    """
    name = provider.strip().lower()

    if name == "lancedb":
        from andino.memory.lancedb_provider import LanceDBProvider

        base_dir = str(resolve_data_path(options.get("base_dir", ".memory")))
        embedding_model = options.get("embedding_model", "amazon.titan-embed-text-v2:0")
        logger.info("memory_provider=lancedb base_dir=%s agent=%s", base_dir, agent_name)
        return LanceDBProvider(base_dir, agent_name, embedding_model)

    raise ValueError(f"Unknown memory provider: {name}. Available: lancedb")
