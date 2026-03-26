"""Abstract memory provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel


class MemoryEntry(BaseModel):
    """A single memory record."""

    id: str
    content: str
    metadata: dict[str, Any] = {}
    created_at: str
    score: float | None = None


class MemoryProvider(ABC):
    """Interface for pluggable memory backends.

    Implementations store and retrieve long-term memories for an agent.
    Each provider is scoped to a single agent (one DB/directory per agent).
    """

    @abstractmethod
    async def store(self, content: str, metadata: dict[str, Any] | None = None) -> MemoryEntry:
        """Store a new memory and return the created entry."""

    @abstractmethod
    async def retrieve(self, query: str, max_results: int = 10) -> list[MemoryEntry]:
        """Semantic search — return memories ranked by relevance."""

    @abstractmethod
    async def list_memories(self, max_results: int = 50) -> list[MemoryEntry]:
        """List recent memories (newest first)."""

    @abstractmethod
    async def get(self, memory_id: str) -> MemoryEntry | None:
        """Get a specific memory by ID."""

    @abstractmethod
    async def delete(self, memory_id: str) -> bool:
        """Delete a memory. Returns True if found and deleted."""
