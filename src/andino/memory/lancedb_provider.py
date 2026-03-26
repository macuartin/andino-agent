"""LanceDB + Bedrock Titan Embeddings memory provider."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from andino.memory.provider import MemoryEntry, MemoryProvider

logger = logging.getLogger(__name__)

_DEFAULT_TABLE = "memories"
_DEFAULT_EMBEDDING_MODEL = "amazon.titan-embed-text-v2:0"
_EMBEDDING_DIM = 1024  # Titan v2 output dimension


class LanceDBProvider(MemoryProvider):
    """Memory backed by LanceDB (embedded) with Bedrock Titan embeddings.

    Data is stored as Lance files in ``{base_dir}/{agent_name}/``.
    Embeddings are generated via AWS Bedrock ``amazon.titan-embed-text-v2:0``.
    """

    def __init__(
        self,
        base_dir: str,
        agent_name: str,
        embedding_model: str = _DEFAULT_EMBEDDING_MODEL,
    ) -> None:
        self._db_path = str(Path(base_dir) / agent_name)
        self._embedding_model = embedding_model
        self._db: Any = None
        self._table: Any = None
        self._bedrock_client: Any = None

    # ------------------------------------------------------------------
    # Lazy init
    # ------------------------------------------------------------------

    def _get_bedrock_client(self) -> Any:
        if self._bedrock_client is None:
            import boto3

            region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
            self._bedrock_client = boto3.client("bedrock-runtime", region_name=region)
        return self._bedrock_client

    async def _ensure_db(self) -> None:
        if self._db is not None:
            return

        import lancedb

        Path(self._db_path).mkdir(parents=True, exist_ok=True)
        self._db = await lancedb.connect_async(self._db_path)

        # Check if table exists
        tables = await self._db.table_names()
        if _DEFAULT_TABLE in tables:
            self._table = await self._db.open_table(_DEFAULT_TABLE)
        else:
            self._table = None  # created on first store

    async def _ensure_table(self, first_vector: list[float]) -> None:
        """Create table on first insert (LanceDB infers schema from data)."""
        if self._table is not None:
            return

        import pyarrow as pa

        schema = pa.schema([
            pa.field("id", pa.utf8()),
            pa.field("content", pa.utf8()),
            pa.field("metadata_json", pa.utf8()),
            pa.field("created_at", pa.utf8()),
            pa.field("vector", pa.list_(pa.float32(), _EMBEDDING_DIM)),
        ])
        self._table = await self._db.create_table(_DEFAULT_TABLE, schema=schema)

    # ------------------------------------------------------------------
    # Embeddings
    # ------------------------------------------------------------------

    async def _embed(self, text: str) -> list[float]:
        """Generate embedding via Bedrock Titan."""
        client = self._get_bedrock_client()
        body = json.dumps({"inputText": text})

        # Bedrock invoke_model is sync — run in thread to avoid blocking
        response = await asyncio.to_thread(
            client.invoke_model,
            modelId=self._embedding_model,
            body=body,
            contentType="application/json",
            accept="application/json",
        )

        result = json.loads(response["body"].read())
        return result["embedding"]

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    async def store(self, content: str, metadata: dict[str, Any] | None = None) -> MemoryEntry:
        await self._ensure_db()

        now = datetime.now(UTC)
        memory_id = f"mem_{now.strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"
        created_at = now.isoformat()
        meta = metadata or {}

        vector = await self._embed(content)
        await self._ensure_table(vector)

        row = {
            "id": memory_id,
            "content": content,
            "metadata_json": json.dumps(meta),
            "created_at": created_at,
            "vector": vector,
        }
        await self._table.add([row])

        logger.info("memory_stored id=%s chars=%d", memory_id, len(content))
        return MemoryEntry(id=memory_id, content=content, metadata=meta, created_at=created_at)

    async def retrieve(self, query: str, max_results: int = 10) -> list[MemoryEntry]:
        await self._ensure_db()
        if self._table is None:
            return []

        query_vector = await self._embed(query)
        results = await self._table.vector_search(query_vector).limit(max_results).to_list()

        entries = []
        for row in results:
            entries.append(MemoryEntry(
                id=row["id"],
                content=row["content"],
                metadata=json.loads(row["metadata_json"]) if row.get("metadata_json") else {},
                created_at=row["created_at"],
                score=1.0 - row.get("_distance", 0.0),  # LanceDB returns distance, convert to similarity
            ))
        return entries

    async def list_memories(self, max_results: int = 50) -> list[MemoryEntry]:
        await self._ensure_db()
        if self._table is None:
            return []

        # Query all, sort by created_at descending
        results = await self._table.query().limit(max_results).to_list()

        entries = []
        for row in results:
            entries.append(MemoryEntry(
                id=row["id"],
                content=row["content"],
                metadata=json.loads(row["metadata_json"]) if row.get("metadata_json") else {},
                created_at=row["created_at"],
            ))
        # Sort newest first
        entries.sort(key=lambda e: e.created_at, reverse=True)
        return entries

    async def get(self, memory_id: str) -> MemoryEntry | None:
        await self._ensure_db()
        if self._table is None:
            return None

        results = await self._table.query().where(f"id = '{memory_id}'").limit(1).to_list()
        if not results:
            return None

        row = results[0]
        return MemoryEntry(
            id=row["id"],
            content=row["content"],
            metadata=json.loads(row["metadata_json"]) if row.get("metadata_json") else {},
            created_at=row["created_at"],
        )

    async def delete(self, memory_id: str) -> bool:
        await self._ensure_db()
        if self._table is None:
            return False

        # Check exists first
        existing = await self.get(memory_id)
        if existing is None:
            return False

        await self._table.delete(f"id = '{memory_id}'")
        logger.info("memory_deleted id=%s", memory_id)
        return True
