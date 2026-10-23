"""Optional semantic cache: reuse an answer for a differently worded but equivalent final
question, within an exactly matching context partition (see ``keys.semantic_partition``).

Off unless SEMANTIC_CACHE=true and the project opts in. Embeddings come from a configured
embedding model routed through the gateway's own provider adapters. Similarity search
uses pgvector cosine distance, filtered to one partition, so the candidate set per query
stays small.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from tokenshield.cache.models import SemanticCacheEntry


class SemanticIndex:
    def __init__(self, sessionmaker: async_sessionmaker, threshold: float) -> None:  # type: ignore[type-arg]
        self._sessionmaker = sessionmaker
        self._threshold = threshold

    async def nearest(self, partition: str, vector: list[float]) -> tuple[str, float] | None:
        distance = SemanticCacheEntry.embedding.cosine_distance(vector)
        async with self._sessionmaker() as session:
            row = (
                await session.execute(
                    select(SemanticCacheEntry.key_hash, distance.label("d"))
                    .where(
                        SemanticCacheEntry.partition == partition,
                        SemanticCacheEntry.expires_at > datetime.now(UTC),
                    )
                    .order_by(distance)
                    .limit(1)
                )
            ).first()
        if row is None:
            return None
        similarity = 1.0 - float(row.d)
        if similarity < self._threshold:
            return None
        return str(row.key_hash), similarity

    async def add(self, partition: str, key_hash: str, vector: list[float], ttl_s: int) -> None:
        async with self._sessionmaker() as session:
            session.add(
                SemanticCacheEntry(
                    key_hash=key_hash,
                    partition=partition,
                    embedding=vector,
                    expires_at=datetime.now(UTC) + timedelta(seconds=ttl_s),
                )
            )
            await session.commit()

    async def remove(self, key_hashes: list[str]) -> None:
        if not key_hashes:
            return
        async with self._sessionmaker() as session:
            await session.execute(
                delete(SemanticCacheEntry).where(SemanticCacheEntry.key_hash.in_(key_hashes))
            )
            await session.commit()
