"""Ingestion and source-listing endpoints."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rag import fetch, ingest
from app.db import get_db
from app.models import Chunk, TranscriptSource
from app.schemas import IngestResult, SourceOut

router = APIRouter(prefix="/api", tags=["ingest"])


class IngestUrlRequest(BaseModel):
    url: str
    title: str | None = None


@router.post("/ingest/seed", response_model=IngestResult)
async def seed(db: AsyncSession = Depends(get_db)) -> IngestResult:
    stats = await ingest.seed_samples(db)
    await db.commit()
    return IngestResult(**stats.__dict__)


@router.post("/ingest/fetch", response_model=IngestResult)
async def fetch_official(db: AsyncSession = Depends(get_db)) -> IngestResult:
    """Fetch + ingest the official Lenny's Podcast starter pack (50 episodes)."""
    stats = await fetch.fetch_official_dataset(db)
    await db.commit()
    return IngestResult(**stats.__dict__)


@router.post("/ingest", response_model=IngestResult)
async def ingest_local(db: AsyncSession = Depends(get_db)) -> IngestResult:
    """Ingest any transcripts placed in backend/data/transcripts."""
    base = Path(__file__).resolve().parents[2] / "data" / "transcripts"
    if not base.exists():
        raise HTTPException(status_code=400, detail=f"Directory not found: {base}")
    stats = await ingest.ingest_directory(db, base)
    await db.commit()
    return IngestResult(**stats.__dict__)


@router.post("/ingest/url", response_model=IngestResult)
async def ingest_from_url(
    body: IngestUrlRequest, db: AsyncSession = Depends(get_db)
) -> IngestResult:
    stats = await ingest.ingest_url(db, body.url, title=body.title)
    await db.commit()
    return IngestResult(**stats.__dict__)


@router.get("/sources", response_model=list[SourceOut])
async def list_sources(db: AsyncSession = Depends(get_db)) -> list[SourceOut]:
    rows = (
        await db.execute(
            select(
                TranscriptSource,
                func.count(Chunk.id).label("chunk_count"),
            )
            .outerjoin(Chunk, Chunk.source_id == TranscriptSource.id)
            .group_by(TranscriptSource.id)
            .order_by(TranscriptSource.created_at)
        )
    ).all()
    return [
        SourceOut(
            id=s.id,
            episode_id=s.episode_id,
            title=s.title,
            speaker=s.speaker,
            url=s.url,
            published_at=s.published_at,
            chunk_count=count,
        )
        for s, count in rows
    ]
