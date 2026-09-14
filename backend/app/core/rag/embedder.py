"""Embedding service with a deterministic lexical fallback.

Primary path is Ollama embeddings (``nomic-embed-text``). If Ollama is not
running or the embedding model isn't pulled, we fall back to a stable hashing
vectorizer so retrieval still functions (keyword-overlap quality) and the demo
never hard-fails on a missing embedding model.
"""
from __future__ import annotations

import hashlib
import logging
import math
import re

from app.config import get_settings
from app.core.llm.ollama import OllamaEmbedder
from app.core.llm.base import ProviderError

logger = logging.getLogger("app.rag.embedder")

_TOKEN_RE = re.compile(r"[a-z0-9']+", re.IGNORECASE)


def _stable_index(token: str, dim: int) -> int:
    digest = hashlib.md5(token.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") % dim


def lexical_vector(text: str, dim: int) -> list[float]:
    """Deterministic hashing bag-of-words vector (fallback embedding)."""
    vec = [0.0] * dim
    for token in _TOKEN_RE.findall(text.lower()):
        vec[_stable_index(token, dim)] += 1.0
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


class EmbeddingService:
    def __init__(self) -> None:
        settings = get_settings()
        self.dim = settings.embedding_dim
        self._ollama = OllamaEmbedder(
            settings.ollama_base_url,
            settings.ollama_embed_model,
            timeout=settings.ollama_timeout_seconds,
        )
        self._ollama_ok: bool | None = None  # cached availability probe

    async def _ollama_available(self) -> bool:
        if self._ollama_ok is None:
            try:
                emb = await self._ollama.embed("ping")
                self._ollama_ok = bool(emb)
            except ProviderError:
                self._ollama_ok = False
            if self._ollama_ok:
                logger.info("Using Ollama embeddings (%s)", self._ollama.model)
            else:
                logger.warning(
                    "Ollama embeddings unavailable; using lexical fallback vectors"
                )
        return self._ollama_ok

    async def embed(self, text: str) -> list[float]:
        """Embed a single text, preferring Ollama and falling back to lexical."""
        if await self._ollama_available():
            try:
                emb = await self._ollama.embed(text)
                if emb and len(emb) > 0:
                    return emb
            except ProviderError:
                self._ollama_ok = False
        return lexical_vector(text, self.dim)

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if await self._ollama_available():
            try:
                return await self._ollama.embed_batch(texts)
            except Exception:
                self._ollama_ok = False
        return [lexical_vector(t, self.dim) for t in texts]

    @staticmethod
    def cosine(a: list[float], b: list[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a)) or 1.0
        nb = math.sqrt(sum(y * y for y in b)) or 1.0
        return dot / (na * nb)
