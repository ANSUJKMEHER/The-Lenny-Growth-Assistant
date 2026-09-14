"""Conversation/session CRUD endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import Artifact, Conversation, Message
from app.schemas import (
    ArtifactOut,
    ConversationCreate,
    ConversationList,
    ConversationOut,
    ConversationSummary,
    MessageOut,
)

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


def _message_out(m: Message) -> MessageOut:
    return MessageOut(
        id=m.id,
        role=m.role,  # type: ignore[arg-type]
        content=m.content,
        citations=m.citations,
        created_at=m.created_at,
    )


@router.post("", response_model=ConversationOut, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    body: ConversationCreate, db: AsyncSession = Depends(get_db)
) -> ConversationOut:
    conv = Conversation(title=body.title or "New chat", user_id=body.user_id)
    db.add(conv)
    await db.commit()
    await db.refresh(conv)
    return ConversationOut(
        id=conv.id,
        title=conv.title,
        user_id=conv.user_id,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        messages=[],
    )


@router.get("", response_model=ConversationList)
async def list_conversations(db: AsyncSession = Depends(get_db)) -> ConversationList:
    rows = (
        await db.execute(
            select(
                Conversation,
                func.count(Message.id).label("message_count"),
            )
            .outerjoin(Message, Message.conversation_id == Conversation.id)
            .group_by(Conversation.id)
            .order_by(Conversation.updated_at.desc())
        )
    ).all()
    sessions = [
        ConversationSummary(
            id=c.id,
            title=c.title,
            created_at=c.created_at,
            updated_at=c.updated_at,
            message_count=count,
        )
        for c, count in rows
    ]
    return ConversationList(sessions=sessions)


@router.get("/{conversation_id}", response_model=ConversationOut)
async def get_conversation(
    conversation_id: str, db: AsyncSession = Depends(get_db)
) -> ConversationOut:
    conv = await _get_or_404(db, conversation_id)
    msgs = (
        await db.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at)
        )
    ).scalars().all()
    arts = (
        await db.execute(
            select(Artifact)
            .where(Artifact.conversation_id == conversation_id)
            .order_by(Artifact.created_at)
        )
    ).scalars().all()
    return ConversationOut(
        id=conv.id,
        title=conv.title,
        user_id=conv.user_id,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        messages=[_message_out(m) for m in msgs],
        artifacts=[
            ArtifactOut(
                id=a.id,
                kind=a.kind,
                title=a.title,
                content=a.content,
                created_at=a.created_at,
            )
            for a in arts
        ],
    )


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: str, db: AsyncSession = Depends(get_db)
) -> None:
    conv = await _get_or_404(db, conversation_id)
    await db.delete(conv)
    await db.commit()


async def _get_or_404(db: AsyncSession, conversation_id: str) -> Conversation:
    conv = await db.get(Conversation, conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv
