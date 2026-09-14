"""Artifact retrieval endpoint (rendered in the in-app viewer)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import Artifact
from app.schemas import ArtifactOut

router = APIRouter(prefix="/api/artifacts", tags=["artifacts"])


@router.get("/{artifact_id}", response_model=ArtifactOut)
async def get_artifact(
    artifact_id: str, db: AsyncSession = Depends(get_db)
) -> ArtifactOut:
    artifact = await db.get(Artifact, artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return ArtifactOut(
        id=artifact.id,
        kind=artifact.kind,
        title=artifact.title,
        content=artifact.content,
        created_at=artifact.created_at,
    )
