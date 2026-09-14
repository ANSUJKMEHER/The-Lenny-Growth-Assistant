"""Tool execution context shared across the agent and its skills."""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.llm.base import LLMProvider
from app.core.rag.retriever import Retriever
from app.models import Artifact
from app.schemas import Citation


@dataclass
class ToolContext:
    db: AsyncSession
    conversation_id: str
    provider: LLMProvider
    retriever: Retriever
    # Grounding citations collected during this agent run, returned with the
    # assistant message so the UI can display them.
    citations: list[Citation] = field(default_factory=list)
    # Artifacts produced during this run (persisted by skills).
    artifacts: list[Artifact] = field(default_factory=list)

    def add_citation(
        self,
        source_id: str,
        title: str,
        chunk_index: int,
        excerpt: str,
        speaker: str | None = None,
        timestamp: str | None = None,
        url: str | None = None,
    ) -> None:
        self.citations.append(
            Citation(
                source_id=source_id,
                title=title,
                chunk_index=chunk_index,
                excerpt=excerpt,
                speaker=speaker,
                timestamp=timestamp,
                url=url,
            )
        )
