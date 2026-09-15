"""Fetch + ingest transcripts from the official Lenny's Podcast transcript archive.

Source: https://github.com/ChatPRD/lennys-podcast-transcripts

The archive holds 300+ episode transcripts in Markdown under
``episodes/{guest-slug}/transcript.md``, each with YAML frontmatter (guest, title,
publish_date, youtube_url, …) and timestamped speaker dialogue. We enumerate the
``episodes/`` tree with the GitHub Git-Trees API and fetch each transcript from
``raw.githubusercontent.com`` at runtime rather than committing the raw contents.

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

REPO = "ChatPRD/lennys-podcast-transcripts"
API_BASE = f"https://api.github.com/repos/{REPO}"
TREE_URL = f"{API_BASE}/git/trees/main?recursive=1"
RAW_BASE = f"https://raw.githubusercontent.com/{REPO}/main/"
USER_AGENT = "lenny-growth-assistant/0.3"


async def _get(client: httpx.AsyncClient, url: str) -> httpx.Response:
    resp = await client.get(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"},
    )
    resp.raise_for_status()
    return resp


def _episode_paths(tree: dict) -> list[str]:
    """Return ``episodes/<slug>/transcript.md`` paths from a recursive git tree."""
    paths: list[str] = []
    for entry in tree.get("tree") or []:
        path = entry.get("path", "")
        if (
            entry.get("type") == "blob"
            and path.startswith("episodes/")
            and path.endswith("/transcript.md")
        ):
            paths.append(path)
    return sorted(paths)


async def fetch_official_dataset(
    db: AsyncSession,
    limit: int | None = None,
) -> IngestStats:
    """Fetch transcripts from the official archive and ingest them.

    ``limit`` caps the number of episodes (None = fetch every transcript in the
    archive). Ordering follows the slug sort from the Git-Trees API.
    """
    stats = IngestStats()
    embedder = EmbeddingService()

    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        try:
            tree = (await _get(client, TREE_URL)).json()
        except Exception as exc:  # pragma: no cover - depends on network
            stats.errors.append(f"Could not fetch transcript index: {exc}")
            return stats

        paths = _episode_paths(tree)
        if limit is not None:
            paths = paths[:limit]

        for path in paths:
            try:
                raw = (await _get(client, RAW_BASE + path)).text
                meta, body = parse_frontmatter(raw)
                slug = path.split("/")[1]
                title = meta.get("title") or slug.replace("-", " ").title()
                doc_stats, _ = await ingest_document(
                    db,
                    body,
                    title=title,
                    episode_id=slug,
                    url=meta.get("youtube_url") or meta.get("url"),
                    speaker=meta.get("guest"),
                    published_at=parse_date(
                        meta.get("publish_date") or meta.get("date")
                    ),
                    embedder=embedder,
                )
                stats.sources_created += doc_stats.sources_created
                stats.sources_skipped += doc_stats.sources_skipped
                stats.chunks_created += doc_stats.chunks_created
                stats.errors.extend(doc_stats.errors)
                await db.commit()
                logger.info(
                    "Ingested %s (%d chunks, total: %d)",
                    title,
                    doc_stats.chunks_created,
                    stats.chunks_created,
                )
            except Exception as exc:  # pragma: no cover - per-file resilience
                stats.errors.append(f"{path}: {exc}")

    return stats


async def ensure_corpus(db: AsyncSession) -> IngestStats:
    """Make sure the knowledge base has real transcripts.

    On a fresh database, fetch a starter set of transcripts from the official
    Lenny's Podcast archive. If the network is unavailable (or the fetch yields
    nothing), fall back to the bundled sample transcripts so the demo still works
    end-to-end. Idempotent.
    """
    count = (await db.execute(select(func.count(TranscriptSource.id)))).scalar_one()
    if count:
        stats = IngestStats()
        stats.sources_skipped = count
        return stats

    logger.info("Corpus empty — fetching official Lenny's Podcast transcripts")
    stats = await fetch_official_dataset(db, limit=10)
    if stats.sources_created == 0:
        if stats.errors:
            logger.warning(
                "Official fetch produced nothing (%s); seeding bundled samples",
                stats.errors[0] if len(stats.errors) == 1 else f"{len(stats.errors)} errors",
            )
        from app.core.rag.ingest import seed_samples

        stats = await seed_samples(db)
    return stats
