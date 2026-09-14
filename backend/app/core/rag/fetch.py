"""Fetch + ingest the official Lenny's Podcast starter dataset.

Source: https://github.com/LennysNewsletter/lennys-newsletterpodcastdata

The public starter pack contains 50 podcast transcripts + 10 newsletter posts in
AI-friendly Markdown (guest, title, date, and speaker timestamps). Its license
permits personal, non-commercial use including "publishing projects built with
it", so we fetch the files at runtime rather than committing the raw contents.

Fetching is idempotent (ingestion dedupes on content hash) and runs best-effort:
if the network is unavailable, the app gracefully keeps whatever is already
indexed (or falls back to the bundled sample transcripts).
"""
from __future__ import annotations

import logging

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rag.embedder import EmbeddingService
from app.core.rag.ingest import IngestStats, ingest_document, parse_date, parse_frontmatter
from app.models import TranscriptSource

logger = logging.getLogger("app.rag.fetch")

RAW_BASE = "https://raw.githubusercontent.com/LennysNewsletter/lennys-newsletterpodcastdata/main/"
INDEX_URL = RAW_BASE + "index.json"
USER_AGENT = "lenny-growth-assistant/0.2"


async def _get(client: httpx.AsyncClient, url: str) -> httpx.Response:
    resp = await client.get(url, headers={"User-Agent": USER_AGENT})
    resp.raise_for_status()
    return resp


async def fetch_official_dataset(
    db: AsyncSession,
    limit: int | None = None,
    include_newsletters: bool = False,
) -> IngestStats:
    """Fetch the official starter-pack transcripts and ingest them.

    ``limit`` caps the number of podcast episodes (None = all ~50 in the pack).
    ``include_newsletters`` also ingests the newsletter posts.
    """
    stats = IngestStats()
    embedder = EmbeddingService()

    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        try:
            index = (await _get(client, INDEX_URL)).json()
        except Exception as exc:  # pragma: no cover - depends on network
            stats.errors.append(f"Could not fetch official index: {exc}")
            return stats

        podcasts = index.get("podcasts") or []
        for entry in podcasts[:limit]:
            filename = entry.get("filename")
            if not filename or not filename.startswith("podcasts/"):
                continue
            try:
                raw = (await _get(client, RAW_BASE + filename)).text
                meta, body = parse_frontmatter(raw)
                doc_stats, _ = await ingest_document(
                    db,
                    body,
                    title=entry.get("title") or meta.get("title") or filename,
                    episode_id=filename.rsplit("/", 1)[-1].removesuffix(".md"),
                    url=entry.get("post_url") or meta.get("url"),
                    speaker=entry.get("guest") or meta.get("guest"),
                    published_at=parse_date(entry.get("date") or meta.get("date")),
                    embedder=embedder,
                )
                stats.sources_created += doc_stats.sources_created
                stats.sources_skipped += doc_stats.sources_skipped
                stats.chunks_created += doc_stats.chunks_created
                stats.errors.extend(doc_stats.errors)
            except Exception as exc:  # pragma: no cover - per-file resilience
                stats.errors.append(f"{filename}: {exc}")

        if include_newsletters:
            for entry in index.get("newsletters") or []:
                filename = entry.get("filename")
                if not filename:
                    continue
                try:
                    raw = (await _get(client, RAW_BASE + filename)).text
                    meta, body = parse_frontmatter(raw)
                    doc_stats, _ = await ingest_document(
                        db,
                        body,
                        title=entry.get("title") or meta.get("title") or filename,
                        episode_id=filename.rsplit("/", 1)[-1].removesuffix(".md"),
                        url=entry.get("post_url") or meta.get("url"),
                        speaker=entry.get("author") or "Lenny Rachitsky",
                        published_at=parse_date(entry.get("date") or meta.get("date")),
                        embedder=embedder,
                    )
                    stats.sources_created += doc_stats.sources_created
                    stats.chunks_created += doc_stats.chunks_created
                    stats.errors.extend(doc_stats.errors)
                except Exception as exc:  # pragma: no cover
                    stats.errors.append(f"{filename}: {exc}")

    return stats


async def ensure_corpus(db: AsyncSession) -> IngestStats:
    """Make sure the knowledge base has real transcripts.

    On a fresh database, fetch the official Lenny's Podcast starter pack. If the
    network is unavailable (or the fetch yields nothing), fall back to the bundled
    sample transcripts so the demo still works end-to-end. Idempotent.
    """
    count = (await db.execute(select(func.count(TranscriptSource.id)))).scalar_one()
    if count:
        stats = IngestStats()
        stats.sources_skipped = count
        return stats

    logger.info("Corpus empty — fetching official Lenny's Podcast transcripts")
    stats = await fetch_official_dataset(db)
    if stats.sources_created == 0:
        if stats.errors:
            logger.warning(
                "Official fetch produced nothing (%s); seeding bundled samples",
                stats.errors[0] if len(stats.errors) == 1 else f"{len(stats.errors)} errors",
            )
        from app.core.rag.ingest import seed_samples

        stats = await seed_samples(db)
    return stats
