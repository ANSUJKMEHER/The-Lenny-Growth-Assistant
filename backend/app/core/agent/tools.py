"""Grounding tools: search the transcript corpus and list available sources."""
from __future__ import annotations

import json

from sqlalchemy import func, select

from app.config import get_settings
from app.core.agent.context import ToolContext
from app.core.agent.tool import Tool, ToolResult
from app.models import Chunk, TranscriptSource


class SearchTranscriptsTool(Tool):
    name = "search_transcripts"
    description = (
        "Search Lenny's Podcast transcripts for grounded material relevant to a "
        "question. Returns verbatim passages with source titles and episode ids. "
        "Use this before answering any question that requires Lenny's content, and "
        "cite the passages you use."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "A focused search query describing what you need.",
            },
            "top_k": {
                "type": "integer",
                "description": "Number of passages to return (default 5, max 10).",
                "default": 5,
            },
        },
        "required": ["query"],
    }

    async def run(self, ctx: ToolContext, query: str, top_k: int = 5) -> ToolResult:
        settings = get_settings()
        top_k = max(1, min(top_k or settings.retrieval_top_k, 10))
        results = await ctx.retriever.retrieve(ctx.db, query, top_k=top_k)

        if not results:
            return ToolResult(
                content=(
                    "No relevant transcript material was found for that query. "
                    "Tell the user the knowledge base does not cover it and do not invent facts."
                )
            )

        blocks = []
        for r in results:
            blocks.append(
                {
                    "source_id": r.source_id,
                    "title": r.title,
                    "episode_id": r.episode_id,
                    "chunk_index": r.chunk_index,
                    "text": r.text,
                }
            )
            ctx.add_citation(r.source_id, r.title, r.chunk_index, r.text[:280])

        payload = json.dumps({"results": blocks}, ensure_ascii=False, indent=2)
        return ToolResult(content=payload)


class ListSourcesTool(Tool):
    name = "list_sources"
    description = (
        "List the Lenny's Podcast transcripts currently indexed, with episode ids "
        "and chunk counts. Use this to orient yourself about what the knowledge "
        "base contains before searching."
    )
    parameters = {"type": "object", "properties": {}, "required": []}

    async def run(self, ctx: ToolContext, **kwargs) -> ToolResult:
        rows = (
            await ctx.db.execute(
                select(
                    TranscriptSource.id,
                    TranscriptSource.title,
                    TranscriptSource.episode_id,
                    func.count(Chunk.id).label("chunks"),
                )
                .outerjoin(Chunk, Chunk.source_id == TranscriptSource.id)
                .group_by(TranscriptSource.id)
                .order_by(TranscriptSource.created_at)
            )
        ).all()

        if not rows:
            return ToolResult(
                content="No transcripts are indexed yet. Suggest the user run ingestion."
            )

        lines = [
            f"- {title} (episode: {ep or 'n/a'}, chunks: {chunks})"
            for _id, title, ep, chunks in rows
        ]
        return ToolResult(content="Indexed transcripts:\n" + "\n".join(lines))
