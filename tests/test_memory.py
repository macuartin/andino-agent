from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from andino.memory.provider import MemoryEntry, MemoryProvider
from andino.memory.tool import create_memory_tool


class MockProvider(MemoryProvider):
    """In-memory provider for testing."""

    def __init__(self):
        self._store: dict[str, MemoryEntry] = {}

    async def store(self, content, metadata=None):
        entry = MemoryEntry(
            id="mem_test_001",
            content=content,
            metadata=metadata or {},
            created_at="2026-03-26T12:00:00+00:00",
        )
        self._store[entry.id] = entry
        return entry

    async def retrieve(self, query, max_results=10):
        # Simple substring match for testing
        results = [
            MemoryEntry(**{**e.model_dump(), "score": 0.95})
            for e in self._store.values()
            if query.lower() in e.content.lower()
        ]
        return results[:max_results]

    async def list_memories(self, max_results=50):
        return list(self._store.values())[:max_results]

    async def get(self, memory_id):
        return self._store.get(memory_id)

    async def delete(self, memory_id):
        if memory_id in self._store:
            del self._store[memory_id]
            return True
        return False


class TestMemoryEntry:
    def test_minimal(self):
        entry = MemoryEntry(id="m1", content="hello", created_at="2026-01-01T00:00:00Z")
        assert entry.id == "m1"
        assert entry.score is None

    def test_with_score(self):
        entry = MemoryEntry(id="m1", content="hello", created_at="2026-01-01T00:00:00Z", score=0.95)
        assert entry.score == 0.95


class TestMemoryTool:
    @pytest.fixture()
    def provider(self):
        return MockProvider()

    @pytest.fixture()
    def tool(self, provider):
        return create_memory_tool(provider)

    async def test_store(self, tool):
        result = await tool(tool_use_id="t1", action="store", content="User likes Python")
        assert result["status"] == "success"
        assert "mem_test_001" in result["content"][0]["text"]

    async def test_store_requires_content(self, tool):
        result = await tool(tool_use_id="t1", action="store")
        assert result["status"] == "error"

    async def test_retrieve(self, tool, provider):
        await provider.store("User likes Python")
        result = await tool(tool_use_id="t1", action="retrieve", query="Python")
        assert result["status"] == "success"
        assert "Python" in result["content"][0]["text"]

    async def test_retrieve_no_results(self, tool):
        result = await tool(tool_use_id="t1", action="retrieve", query="nonexistent")
        assert "No memories" in result["content"][0]["text"]

    async def test_retrieve_requires_query(self, tool):
        result = await tool(tool_use_id="t1", action="retrieve")
        assert result["status"] == "error"

    async def test_list(self, tool, provider):
        await provider.store("Memory 1")
        result = await tool(tool_use_id="t1", action="list")
        assert result["status"] == "success"
        assert "1 memory" in result["content"][0]["text"]

    async def test_list_empty(self, tool):
        result = await tool(tool_use_id="t1", action="list")
        assert "No memories" in result["content"][0]["text"]

    async def test_get(self, tool, provider):
        await provider.store("Test content")
        result = await tool(tool_use_id="t1", action="get", document_id="mem_test_001")
        assert result["status"] == "success"
        assert "Test content" in result["content"][0]["text"]

    async def test_get_not_found(self, tool):
        result = await tool(tool_use_id="t1", action="get", document_id="nonexistent")
        assert "not found" in result["content"][0]["text"]

    async def test_delete(self, tool, provider):
        await provider.store("To be deleted")
        result = await tool(tool_use_id="t1", action="delete", document_id="mem_test_001")
        assert "deleted" in result["content"][0]["text"]

    async def test_delete_not_found(self, tool):
        result = await tool(tool_use_id="t1", action="delete", document_id="nonexistent")
        assert "not found" in result["content"][0]["text"]

    async def test_unknown_action(self, tool):
        result = await tool(tool_use_id="t1", action="unknown")
        assert result["status"] == "error"

    def test_tool_has_spec(self, tool):
        assert hasattr(tool, "TOOL_SPEC")
        assert tool.TOOL_SPEC["name"] == "memory"

    def test_spec_aligns_with_sdk_keys(self, tool):
        props = tool.TOOL_SPEC["inputSchema"]["properties"]
        # Aligned with strands_tools.memory: same identifier and key fields.
        assert "document_id" in props
        assert "title" in props
        assert "min_score" in props
        # Andino extension preserved.
        assert "tags" in props

    async def test_store_with_title(self, tool, provider):
        result = await tool(
            tool_use_id="t1",
            action="store",
            content="X",
            title="My title",
            tags=["a"],
        )
        assert result["status"] == "success"
        stored = await provider.get("mem_test_001")
        assert stored.metadata["title"] == "My title"
        assert stored.metadata["tags"] == ["a"]

    async def test_retrieve_min_score_filters(self, tool, provider):
        # MockProvider gives all retrieved entries score=0.95
        await provider.store("Python is great")
        high = await tool(tool_use_id="t1", action="retrieve", query="Python", min_score=0.5)
        assert "Python is great" in high["content"][0]["text"]
        low = await tool(tool_use_id="t1", action="retrieve", query="Python", min_score=0.99)
        assert "No memories" in low["content"][0]["text"]


class TestBuildMemoryProvider:
    def test_unknown_provider(self):
        from andino.memory import build_memory_provider

        with pytest.raises(ValueError, match="Unknown memory provider"):
            build_memory_provider("test-agent", "nosql", {})

    @patch("andino.memory.lancedb_provider.LanceDBProvider")
    def test_lancedb_provider(self, mock_cls):
        from andino.memory import build_memory_provider

        mock_cls.return_value = MagicMock()
        result = build_memory_provider("sre", "lancedb", {"base_dir": "/tmp/mem"})
        assert result is mock_cls.return_value
