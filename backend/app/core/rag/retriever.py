"""Retrieval: hybrid semantic (embedding) + lexical (BM25) search.

Strategy is chosen per-query: if chunk embeddings exist and the embedding
service is reachable, use cosine similarity; otherwise fall back to a small
BM25 scorer so grounding never silently returns empty results.
"""
from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Chunk, TranscriptSource
from app.core.rag.embedder import EmbeddingService

logger = logging.getLogger("app.rag.retriever")

_TOKEN_RE = re.compile(r"[a-z0-9']+", re.IGNORECASE)

# BM25 constants (tuned for short technical passages).
_BM25_K1 = 1.5
_BM25_B = 0.75


@dataclass
class RetrievedChunk:
    chunk_id: str
    text: str
    source_id: str
    title: str
    episode_id: str | None
    chunk_index: int
    score: float
    method: str  # "embedding" | "bm25"
    speaker: str | None = None
    timestamp: str | None = None
    url: str | None = None


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


class _BM25:
    def __init__(self, docs: list[list[str]]) -> None:
        self.docs = docs
        self.n = len(docs)
        self.avgdl = (sum(len(d) for d in docs) / self.n) if self.n else 1.0
        self.df: dict[str, int] = {}
        for d in docs:
            for term in set(d):
                self.df[term] = self.df.get(term, 0) + 1

    def _idf(self, term: str) -> float:
        df = self.df.get(term, 0)
        return math.log(1 + (self.n - df + 0.5) / (df + 0.5))

    def score(self, query: list[str], doc: list[str]) -> float:
        if not doc:
            return 0.0
        tf: dict[str, int] = {}
        for t in doc:
            tf[t] = tf.get(t, 0) + 1
        dl = len(doc)
        total = 0.0
        for term in query:
            if term not in tf:
                continue
            freq = tf[term]
            denom = freq + _BM25_K1 * (1 - _BM25_B + _BM25_B * dl / self.avgdl)
            total += self._idf(term) * freq * (_BM25_K1 + 1) / denom
        return total


class Retriever:
    def __init__(self) -> None:
        self.embedder = EmbeddingService()

    async def retrieve(
        self, db: AsyncSession, query: str, top_k: int = 6
    ) -> list[RetrievedChunk]:
        """Retrieve the top-k most relevant chunks with source metadata."""
        stmt = (
            select(Chunk, TranscriptSource)
            .join(TranscriptSource, Chunk.source_id == TranscriptSource.id)
        )
        rows = (await db.execute(stmt)).all()
        if not rows:
            logger.info("Retrieval: no chunks indexed")
            return []

        chunks: list[tuple[Chunk, TranscriptSource]] = [(c, s) for c, s in rows]

        # Prefer semantic search if embeddings are present.
        if any(c.embedding for c, _ in chunks):
            try:
                qvec = await self.embedder.embed(query)
                scored = []
                for c, s in chunks:
                    sim = self.embedder.cosine(qvec, c.embedding or [])
                    scored.append((sim, c, s))
                scored.sort(key=lambda t: t[0], reverse=True)
                return [
                    self._to_result(c, s, sim, "embedding")
                    for sim, c, s in scored[:top_k]
                    if sim > 0
                ]
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Embedding retrieval failed, falling back to BM25: %s", exc)

        # Lexical fallback.
        corpus = [self._tokenize(c.text) for c, _ in chunks]
        bm25 = _BM25(corpus)
        qterms = self._tokenize(query)
        scored = sorted(
            ((bm25.score(qterms, corpus[i]), chunks[i]) for i in range(len(chunks))),
            key=lambda t: t[0],
            reverse=True,
        )
        # No matches means no matches: return [] so the assistant honestly
        # reports that the knowledge base does not cover the question, instead
        # of being handed an irrelevant chunk it might cite as relevant.
        return [
            self._to_result(c, s, score, "bm25")
            for score, (c, s) in scored[:top_k]
            if score > 0
        ]

    @staticmethod
    def _to_result(
        chunk: Chunk, source: TranscriptSource, score: float, method: str
    ) -> RetrievedChunk:
        return RetrievedChunk(
            chunk_id=chunk.id,
            text=chunk.text,
            source_id=source.id,
            title=source.title,
            episode_id=source.episode_id,
            chunk_index=chunk.index,
            score=round(float(score), 4),
            method=method,
            speaker=chunk.speaker,
            timestamp=chunk.timestamp,
            url=source.url,
        )
