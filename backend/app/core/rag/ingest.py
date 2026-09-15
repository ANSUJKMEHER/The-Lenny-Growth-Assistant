"""Ingestion pipeline.

Loads transcripts from local Markdown/text files, seed samples, or URLs,
chunks them, embeds the chunks, and persists everything to PostgreSQL with a
content hash for idempotent re-ingestion (re-running never duplicates data).
"""
from __future__ import annotations

import hashlib
import ipaddress
import logging
import re
import socket
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.rag.chunker import chunk_speaker_turns, chunk_text
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
            meta[k.strip().lower()] = v.strip().strip('\"\'')
    return meta, text[m.end():]


def parse_date(value: str | None) -> datetime | None:
    """Parse a frontmatter date (``YYYY-MM-DD`` or ISO-8601) into a datetime."""
    if not value:
        return None
    value = value.strip().strip('\"\'')
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            return datetime.strptime(value[:10], "%Y-%m-%d")
        except ValueError:
            return None


def _extract_text_from_html(html: str) -> str:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "nav", "footer", "header"]):
        tag.decompose()
    return soup.get_text("\n")


def _validate_public_url(url: str) -> str | None:
    """Return a reason ``url`` is unsafe to fetch server-side, else ``None``.

    Rejects non-http(s) schemes and hostnames that resolve to a non-global
    address (loopback, private, link-local incl. cloud metadata, reserved,
    multicast). This blocks SSRF against the host and internal services.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return "only http(s) URLs are allowed"
    host = parsed.hostname
    if not host:
        return "URL has no hostname"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        infos = socket.getaddrinfo(host, port)
    except socket.gaierror:
        return "could not resolve hostname"
    for info in infos:
        raw_ip = info[4][0]
        try:
            addr = ipaddress.ip_address(raw_ip)
        except ValueError:
            return "could not resolve hostname"
        if not addr.is_global:
            return "URL resolves to a non-public address"
    return None


async def ingest_document(
    db: AsyncSession,
    text: str,
    *,
    title: str,
    episode_id: str | None = None,
    url: str | None = None,
    speaker: str | None = None,
    published_at: datetime | None = None,
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
        published_at=published_at,
        content_hash=digest,
    )
    db.add(source)
    await db.flush()  # get source.id

    # Prefer speaker-turn chunking when the transcript is speaker-labelled
    # (e.g. the official Lenny podcast format), which records speaker +
    # timestamp per chunk for deep citations.
    speaker_chunks = chunk_speaker_turns(
        text,
        target_tokens=settings.chunk_target_tokens,
        overlap_tokens=settings.chunk_overlap_tokens,
    )
    if speaker_chunks:
        chunks = speaker_chunks
    else:
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
                speaker=getattr(chunk, "speaker", None),
                timestamp=getattr(chunk, "timestamp", None),
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
                speaker=meta.get("speaker") or meta.get("guest"),
                published_at=parse_date(meta.get("date")),
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
    """Fetch a transcript page and ingest its extracted text.

    The URL is validated against SSRF (http(s) + public address only) and every
    redirect is re-validated before it is followed, so this endpoint cannot be
    used to probe internal services or the instance's cloud metadata.
    """
    import httpx

    stats = IngestStats()
    reason = _validate_public_url(url)
    if reason:
        stats.errors.append(f"Refused to fetch {url}: {reason}")
        return stats

    current = url
    max_redirects = 3
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=False) as client:
            for _ in range(max_redirects + 1):
                reason = _validate_public_url(current)
                if reason:
                    stats.errors.append(f"Refused to follow {current}: {reason}")
                    return stats
                resp = await client.get(
                    current, headers={"User-Agent": "lenny-growth-assistant/0.2"}
                )
                if resp.status_code in (301, 302, 303, 307, 308):
                    location = resp.headers.get("location")
                    if not location:
                        break
                    current = urljoin(current, location)
                    continue
                break
            else:
                stats.errors.append(f"Too many redirects fetching {url}")
                return stats
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
