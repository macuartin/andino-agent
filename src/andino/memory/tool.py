"""Memory tool factory for Strands agents."""

from __future__ import annotations

import logging
from typing import Any

from andino.memory.provider import MemoryProvider

logger = logging.getLogger(__name__)

TOOL_SPEC: dict[str, Any] = {
    "name": "memory",
    "description": (
        "Store and retrieve long-term memories that persist across conversations. "
        "Use this to remember important facts, user preferences, project context, "
        "past decisions, and anything the agent should recall in future sessions.\n\n"
        "Actions:\n"
        "- store: Save a new memory with optional tags\n"
        "- retrieve: Semantic search — find memories related to a query\n"
        "- list: Show recent memories (newest first)\n"
        "- get: Fetch a specific memory by ID\n"
        "- delete: Remove a memory by ID"
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["store", "retrieve", "list", "get", "delete"],
                "description": "The action to perform.",
            },
            "content": {
                "type": "string",
                "description": "Content to store (required for 'store' action).",
            },
            "query": {
                "type": "string",
                "description": "Search query (required for 'retrieve' action).",
            },
            "memory_id": {
                "type": "string",
                "description": "Memory ID (required for 'get' and 'delete' actions).",
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Tags for categorization (optional, for 'store' action).",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum results to return (default: 10 for retrieve, 50 for list).",
            },
        },
        "required": ["action"],
    },
}


def create_memory_tool(provider: MemoryProvider) -> Any:
    """Create a Strands-compatible memory tool backed by the given provider.

    Returns a callable with a ``TOOL_SPEC`` attribute (legacy tool pattern).
    """

    async def memory(tool_use_id: str, **kwargs: Any) -> dict:
        action = kwargs.get("action", "")

        if action == "store":
            content = kwargs.get("content", "")
            if not content:
                return _err("'content' is required for store action.")
            tags = kwargs.get("tags", [])
            entry = await provider.store(content, {"tags": tags})
            return _ok(f"Memory stored.\nID: {entry.id}\nContent: {entry.content}")

        if action == "retrieve":
            query = kwargs.get("query", "")
            if not query:
                return _err("'query' is required for retrieve action.")
            max_results = kwargs.get("max_results", 10)
            entries = await provider.retrieve(query, max_results)
            if not entries:
                return _ok("No memories found matching the query.")
            lines = [f"Found {len(entries)} memory(s):"]
            for e in entries:
                score = f" (relevance: {e.score:.2f})" if e.score is not None else ""
                tags = e.metadata.get("tags", [])
                tag_str = f" [{', '.join(tags)}]" if tags else ""
                lines.append(f"\n**{e.id}**{score}{tag_str}\n{e.content}")
            return _ok("\n".join(lines))

        if action == "list":
            max_results = kwargs.get("max_results", 50)
            entries = await provider.list_memories(max_results)
            if not entries:
                return _ok("No memories stored yet.")
            lines = [f"{len(entries)} memory(s):"]
            for e in entries:
                preview = e.content[:100] + "..." if len(e.content) > 100 else e.content
                lines.append(f"- {e.id} ({e.created_at[:10]}): {preview}")
            return _ok("\n".join(lines))

        if action == "get":
            memory_id = kwargs.get("memory_id", "")
            if not memory_id:
                return _err("'memory_id' is required for get action.")
            entry = await provider.get(memory_id)
            if entry is None:
                return _ok(f"Memory '{memory_id}' not found.")
            return _ok(
                f"ID: {entry.id}\n"
                f"Created: {entry.created_at}\n"
                f"Tags: {entry.metadata.get('tags', [])}\n"
                f"Content:\n{entry.content}"
            )

        if action == "delete":
            memory_id = kwargs.get("memory_id", "")
            if not memory_id:
                return _err("'memory_id' is required for delete action.")
            ok = await provider.delete(memory_id)
            if ok:
                return _ok(f"Memory '{memory_id}' deleted.")
            return _ok(f"Memory '{memory_id}' not found.")

        return _err(f"Unknown action: {action}. Use: store, retrieve, list, get, delete.")

    memory.TOOL_SPEC = TOOL_SPEC
    return memory


def _ok(text: str) -> dict:
    return {"status": "success", "content": [{"text": text}]}


def _err(text: str) -> dict:
    return {"status": "error", "content": [{"text": text}]}
