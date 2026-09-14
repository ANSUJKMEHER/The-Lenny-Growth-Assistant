"""Pydantic request/response schemas — the API contract.

Every endpoint validates input and returns a structured JSON shape so the
client and the evaluator know exactly what to expect. Errors use a single
:class:`ErrorResponse` envelope (see docs/architecture.md).
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Role = Literal["user", "assistant", "system"]


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #
class ErrorResponse(BaseModel):
    error: str
    detail: str | None = None
    code: str | None = None


# --------------------------------------------------------------------------- #
# Sessions & messages
# --------------------------------------------------------------------------- #
class ConversationCreate(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    user_id: str | None = Field(default=None, max_length=128)


class Citation(BaseModel):
    source_id: str
    title: str
    chunk_index: int
    excerpt: str


class MessageOut(BaseModel):
    id: str
    role: Role
    content: str
    citations: list[Citation] | None = None
    created_at: datetime


class ArtifactOut(BaseModel):
    id: str
    kind: str
    title: str
    content: str
    created_at: datetime


class ConversationOut(BaseModel):
    id: str
    title: str
    user_id: str | None = None
    created_at: datetime
    updated_at: datetime
    messages: list[MessageOut] = Field(default_factory=list)
    artifacts: list[ArtifactOut] = Field(default_factory=list)


class ConversationSummary(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int


class ConversationList(BaseModel):
    sessions: list[ConversationSummary]


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=20_000)


class ChatResponse(BaseModel):
    message: MessageOut
    artifacts: list[ArtifactOut] = Field(default_factory=list)
    provider: str
    model: str
    grounded: bool


# --------------------------------------------------------------------------- #
# Provider / config
# --------------------------------------------------------------------------- #
class ProviderInfo(BaseModel):
    name: str
    model: str
    available: bool
    reason: str | None = None


class ConfigOut(BaseModel):
    provider: str
    model: str
    providers: list[ProviderInfo]
    fallback_enabled: bool


class ConfigUpdate(BaseModel):
    provider: Literal["ollama", "anthropic", "openai"]
    model: str | None = None


# --------------------------------------------------------------------------- #
# Ingestion
# --------------------------------------------------------------------------- #
class IngestResult(BaseModel):
    sources_created: int
    sources_skipped: int
    chunks_created: int
    errors: list[str] = Field(default_factory=list)


class SourceOut(BaseModel):
    id: str
    episode_id: str | None
    title: str
    speaker: str | None
    url: str | None
    published_at: datetime | None
    chunk_count: int
