"""Chat: send a message and run the grounded agent."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.agent.agent import Agent
from app.core.agent.context import ToolContext
from app.core.llm.base import ChatMessage, ProviderError
from app.core.llm.factory import resolve_provider
from app.core.rag.retriever import Retriever
from app.core import settings_store
from app.db import get_db
from app.models import Artifact, Conversation, Message
from app.schemas import ArtifactOut, ChatResponse, MessageCreate, MessageOut

logger = logging.getLogger("app.api.chat")

router = APIRouter(prefix="/api/sessions", tags=["chat"])


@router.post("/{conversation_id}/messages", response_model=ChatResponse)
async def send_message(
    conversation_id: str,
    body: MessageCreate,
    db: AsyncSession = Depends(get_db),
) -> ChatResponse:
    conv = await db.get(Conversation, conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Persist the user turn.
    user_msg = Message(conversation_id=conversation_id, role="user", content=body.content)
    db.add(user_msg)
    await db.flush()

    # Build conversation history from prior turns (excluding the just-added user msg
    # which we append explicitly below).
    prior = (
        await db.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at)
        )
    ).scalars().all()
    history = [
        ChatMessage(role=m.role, content=m.content)
        for m in prior
        if m.role in ("user", "assistant") and m.id != user_msg.id
    ]
    history.append(ChatMessage(role="user", content=body.content))

    # Resolve provider (with fallback) and run the agent.
    try:
        provider = await resolve_provider(db)
    except ProviderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    ctx = ToolContext(
        db=db,
        conversation_id=conversation_id,
        provider=provider,
        retriever=Retriever(),
    )
    agent = Agent(provider)
    try:
        result = await agent.run(ctx, history)
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=f"LLM failure: {exc}") from exc
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Agent run failed")
        raise HTTPException(status_code=500, detail=f"Agent error: {exc}") from exc

    # Persist the assistant turn + citations.
    assistant_msg = Message(
        conversation_id=conversation_id,
        role="assistant",
        content=result.content,
        citations=[c.model_dump() for c in ctx.citations] if ctx.citations else None,
    )
    db.add(assistant_msg)

    # Auto-title the conversation on its first exchange.
    if conv.title == "New chat" or conv.title is None:
        conv.title = _derive_title(body.content)

    # Collect artifacts created by skills.
    artifact_outs: list[ArtifactOut] = []
    for artifact in ctx.artifacts:
        artifact.message_id = assistant_msg.id
        artifact_outs.append(
            ArtifactOut(
                id=artifact.id,
                kind=artifact.kind,
                title=artifact.title,
                content=artifact.content,
                created_at=artifact.created_at,
            )
        )

    await db.commit()

    return ChatResponse(
        message=MessageOut(
            id=assistant_msg.id,
            role="assistant",
            content=assistant_msg.content,
            citations=assistant_msg.citations,
            created_at=assistant_msg.created_at,
        ),
        artifacts=artifact_outs,
        provider=provider.name,
        model=provider.model,
        grounded=result.grounded,
    )


def _derive_title(user_text: str) -> str:
    clean = " ".join(user_text.split())
    return clean[:60] + ("…" if len(clean) > 60 else "")
