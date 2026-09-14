"""Chat: send a message and run the grounded agent.

Two paths share the same agent/retrieval/persistence logic:
- ``POST /api/sessions/{id}/messages``            — non-streaming JSON response.
- ``POST /api/sessions/{id}/messages/stream``     — Server-Sent Events (SSE).
"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.agent.claude_sdk_agent import SDKUnavailableError, select_agent
from app.core.agent.context import ToolContext
from app.core.llm.base import ChatMessage, LLMProvider, ProviderError
from app.core.llm.factory import resolve_provider
from app.core.rag.retriever import Retriever
from app.db import get_db
from app.models import Conversation, Message
from app.schemas import ArtifactOut, ChatResponse, MessageCreate, MessageOut

logger = logging.getLogger("app.api.chat")

router = APIRouter(prefix="/api/sessions", tags=["chat"])

# Friendly client-facing progress labels for each tool the agent can invoke.
_TOOL_STATUS = {
    "search_transcripts": "Searching Lenny's Podcast transcripts…",
    "list_sources": "Checking the knowledge base…",
    "write_ship30_essay": "Writing your Ship 30 for 30 essay…",
    "generate_artifact": "Generating your artifact…",
}


async def _load_history(
    db: AsyncSession, conversation_id: str, user_msg: Message
) -> list[ChatMessage]:
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
    history.append(ChatMessage(role="user", content=user_msg.content))
    return history


async def _finalize_turn(
    db: AsyncSession,
    conv: Conversation,
    user_msg: Message,
    ctx: ToolContext,
    provider: LLMProvider,
    content: str,
    grounded: bool,
) -> ChatResponse:
    """Persist the assistant turn + citations + artifacts and commit."""
    assistant_msg = Message(
        conversation_id=conv.id,
        role="assistant",
        content=content,
        citations=[c.model_dump() for c in ctx.citations] if ctx.citations else None,
    )
    db.add(assistant_msg)
    await db.flush()

    if conv.title == "New chat" or conv.title is None:
        conv.title = _derive_title(user_msg.content)

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
        grounded=grounded,
    )


async def _prepare_turn(
    conversation_id: str,
    body: MessageCreate,
    db: AsyncSession,
) -> tuple[Conversation, Message, ToolContext, object, list[ChatMessage]]:
    """Shared preamble for both chat paths: validate, persist user turn, resolve."""
    conv = await db.get(Conversation, conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    user_msg = Message(conversation_id=conversation_id, role="user", content=body.content)
    db.add(user_msg)
    await db.flush()

    history = await _load_history(db, conversation_id, user_msg)

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

    try:
        agent = select_agent(provider)
    except SDKUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return conv, user_msg, ctx, agent, history


@router.post("/{conversation_id}/messages", response_model=ChatResponse)
async def send_message(
    conversation_id: str,
    body: MessageCreate,
    db: AsyncSession = Depends(get_db),
) -> ChatResponse:
    conv, user_msg, ctx, agent, history = await _prepare_turn(conversation_id, body, db)

    try:
        result = await agent.run(ctx, history)
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=f"LLM failure: {exc}") from exc
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Agent run failed")
        raise HTTPException(status_code=500, detail=f"Agent error: {exc}") from exc

    return await _finalize_turn(
        db, conv, user_msg, ctx, ctx.provider, result.content, result.grounded
    )


@router.post("/{conversation_id}/messages/stream")
async def send_message_stream(
    conversation_id: str,
    body: MessageCreate,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    conv, user_msg, ctx, agent, history = await _prepare_turn(conversation_id, body, db)

    def sse(payload: dict) -> str:
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    async def event_stream():
        run_stream = getattr(agent, "run_stream", None)
        # Emit immediate feedback so the UI shows activity before the first
        # token arrives (local models can take a while to warm up).
        yield sse({"type": "status", "data": "Thinking…"})
        try:
            if run_stream is None:
                # Non-streaming runtime (e.g. the Claude Agent SDK path): run
                # once and emit the full answer as a single token event.
                result = await agent.run(ctx, history)
                yield sse({"type": "token", "data": result.content})
                response = await _finalize_turn(
                    db, conv, user_msg, ctx, ctx.provider, result.content, result.grounded
                )
                yield sse({"type": "done", "data": response.model_dump(mode="json")})
                return

            result = None
            async for ev in run_stream(ctx, history):
                if ev.kind == "token":
                    yield sse({"type": "token", "data": ev.data})
                elif ev.kind == "tool":
                    yield sse(
                        {
                            "type": "status",
                            "data": _TOOL_STATUS.get(ev.data, f"Using {ev.data}…"),
                        }
                    )
                elif ev.kind == "done":
                    result = ev.result

            response = await _finalize_turn(
                db, conv, user_msg, ctx, ctx.provider, result.content, result.grounded
            )
            yield sse({"type": "done", "data": response.model_dump(mode="json")})
        except ProviderError as exc:
            yield sse({"type": "error", "data": f"LLM failure: {exc}"})
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Agent stream failed")
            yield sse({"type": "error", "data": f"Agent error: {exc}"})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


def _derive_title(user_text: str) -> str:
    clean = " ".join(user_text.split())
    return clean[:60] + ("…" if len(clean) > 60 else "")
