"""Ingestion pipeline.

Loads transcripts from local Markdown/text files, seed samples, or URLs,
chunks them, embeds the chunks, and persists everything to PostgreSQL with a
content hash for idempotent re-ingestion (re-running never duplicates data).
"""
from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.rag.chunker import chunk_text
from app.core.rag.embedder import EmbeddingService
from app.models import Chunk, TranscriptSource

logger = logging.getLogger("app.rag.ingest")

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


@dataclass
class IngestStats:
    sources_created: int = 0
    sources_skipped: int = 0
    chunks_created: int = 0
    errors: list[str] = field(default_factory=list)


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Split optional ``---\nkey: value\n---`` frontmatter from a transcript."""
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    meta: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip().lower()] = v.strip()
    return meta, text[m.end():]


def _extract_text_from_html(html: str) -> str:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "nav", "footer", "header"]):
        tag.decompose()
    return soup.get_text("\n")


async def ingest_document(
    db: AsyncSession,
    text: str,
    *,
    title: str,
    episode_id: str | None = None,
    url: str | None = None,
    speaker: str | None = None,
    embedder: EmbeddingService | None = None,
) -> tuple[IngestStats, TranscriptSource | None]:
    """Ingest a single transcript document (idempotent by content hash)."""
    settings = get_settings()
    embedder = embedder or EmbeddingService()
    stats = IngestStats()

    text = text.strip()
    if not text:
        stats.errors.append(f"Empty transcript: {title}")
        return stats, None

    digest = _content_hash(text)
    existing = (
        await db.execute(
            select(TranscriptSource).where(TranscriptSource.content_hash == digest)
        )
    ).scalar_one_or_none()
    if existing:
        stats.sources_skipped += 1
        return stats, existing

    source = TranscriptSource(
        episode_id=episode_id,
        title=title[:512],
        speaker=speaker,
        url=url,
        content_hash=digest,
    )
    db.add(source)
    await db.flush()  # get source.id

    chunks = chunk_text(
        text,
        target_tokens=settings.chunk_target_tokens,
        overlap_tokens=settings.chunk_overlap_tokens,
    )
    try:
        vectors = await embedder.embed_many([c.text for c in chunks])
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Embedding failed during ingest, storing chunks without vectors: %s", exc)
        vectors = [None] * len(chunks)

    for chunk, vec in zip(chunks, vectors):
        db.add(
            Chunk(
                source_id=source.id,
                index=chunk.index,
                text=chunk.text,
                embedding=vec,
                token_count=chunk.token_count,
            )
        )

    stats.sources_created += 1
    stats.chunks_created += len(chunks)
    return stats, source


async def ingest_directory(db: AsyncSession, directory: Path) -> IngestStats:
    """Ingest every ``.md``/``.txt`` file in a directory."""
    settings = get_settings()
    embedder = EmbeddingService()
    stats = IngestStats()

    files = sorted(
        [*directory.glob("*.md"), *directory.glob("*.txt")]
    )
    if not files:
        stats.errors.append(f"No .md/.txt transcripts found in {directory}")
        return stats

    for path in files:
        try:
            raw = path.read_text(encoding="utf-8")
            meta, body = parse_frontmatter(raw)
            doc_stats, _ = await ingest_document(
                db,
                body,
                title=meta.get("title") or path.stem.replace("-", " ").title(),
                episode_id=meta.get("episode_id"),
                url=meta.get("url"),
                speaker=meta.get("speaker"),
                embedder=embedder,
            )
            stats.sources_created += doc_stats.sources_created
            stats.sources_skipped += doc_stats.sources_skipped
            stats.chunks_created += doc_stats.chunks_created
            stats.errors.extend(doc_stats.errors)
        except Exception as exc:
            stats.errors.append(f"{path.name}: {exc}")

    return stats


async def ingest_url(db: AsyncSession, url: str, title: str | None = None) -> IngestStats:
    """Fetch a transcript page and ingest its extracted text."""
    import httpx

    stats = IngestStats()
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": "lenny-growth-assistant/0.1"})
        resp.raise_for_status()
    except Exception as exc:
        stats.errors.append(f"Failed to fetch {url}: {exc}")
        return stats

    text = _extract_text_from_html(resp.text)
    doc_stats, _ = await ingest_document(
        db, text, title=title or url, url=url
    )
    stats.sources_created += doc_stats.sources_created
    stats.chunks_created += doc_stats.chunks_created
    stats.errors.extend(doc_stats.errors)
    return stats


async def seed_samples(db: AsyncSession) -> IngestStats:
    """Ingest the bundled sample transcripts (see backend/data/transcripts)."""
    base = Path(__file__).resolve().parents[2] / "data" / "transcripts"
    if not base.exists():
        stats = IngestStats()
        stats.errors.append(f"Seed directory not found: {base}")
        return stats
    return await ingest_directory(db, base)
