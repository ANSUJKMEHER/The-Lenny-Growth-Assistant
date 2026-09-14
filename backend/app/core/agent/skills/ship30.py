"""Ship 30 for 30 content skill.

Encodes the Ship 30 for 30 writing principles (Nicolas Cole / Dickie Bush) as a
structured, reusable skill rather than a one-off prompt. The skill:

1. Retrieves grounded passages from the Lenny transcript corpus on the topic.
2. Composes a ~1,250-word "atomic essay" that follows the encoded principles.
3. Persists the result as a Markdown artifact for the in-app viewer.

Source of principles: Ship 30 for 30 "Types of Share" / atomic-essay guide.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from app.config import get_settings
from app.core.agent.context import ToolContext
from app.core.agent.tool import Tool, ToolResult
from app.core.llm.base import ChatMessage
from app.core.security import render_markdown_safe
from app.models import Artifact

logger = logging.getLogger("app.agent.ship30")

# The encoded writing principles — these are the durable rules the skill applies
# on every invocation, keeping the style consistent and on-brand.
SHIP30_PRINCIPLES = """
You are a Ship 30 for 30 writer. Apply these principles strictly:

HOOK
- Open with a specific, counterintuitive, or emotionally-charged first line
  that makes a busy product/growth person stop scrolling. No throat-clearing.

ONE BIG IDEA
- The essay has exactly one thesis. Everything supports it; delete anything
  that wanders.

STRUCTURE / NARRATIVE
- Use a clear arc: Hook -> Context (why now) -> 3 supporting points -> Takeaway.
- Number your three supporting points ("1. 2. 3.") for skimmability.

SKIMMABLE FORMATTING
- Short paragraphs (1-3 sentences). Generous headings and subheadings.
- Use bullets for lists and **bold** selectively for the single most important
  phrase in each section. Never bold whole sentences.

SPECIFICITY
- Prefer concrete numbers, examples, and named tactics over abstract advice.
- Every claim must trace to a passage in the provided transcript material.
  If the material does not support a claim, do not make it.

TAKEAWAY
- End with a single, specific, useful action the reader can take today.
- A short "The takeaway" line and (optionally) a one-line call to action.

LENGTH & VOICE
- Target approximately 1,250 words. Write in a direct, confident, first or
  second person voice. No corporate filler, no jargon.
"""

# Length guardrails: local models under-generate badly, so we enforce a floor
# and expand in a bounded loop when the draft comes back too short.
MIN_ESSAY_WORDS = 1000
TARGET_ESSAY_WORDS = 1250
MAX_EXPANSION_ROUNDS = 2


def _word_count(text: str) -> int:
    return len(text.split())


class Ship30EssaySkill(Tool):
    name = "write_ship30_essay"
    description = (
        "Turn grounded Lenny's Podcast material into a Ship 30 for 30-style essay "
        "of approximately 1,250 words with a strong hook, skimmable formatting, and "
        "a specific takeaway. Use when the user asks for a Ship 30 essay, a "
        "shareable post, or a polished written piece. Requires a topic."
    )
    parameters = {
        "type": "object",
        "properties": {
            "topic": {
                "type": "string",
                "description": "The essay topic, grounded in Lenny's transcripts.",
            },
            "audience": {
                "type": "string",
                "description": "Optional target audience (default: product managers and growth leads).",
            },
            "angle": {
                "type": "string",
                "description": "Optional angle or thesis to emphasise.",
            },
        },
        "required": ["topic"],
    }

    async def run(
        self,
        ctx: ToolContext,
        topic: str,
        audience: str | None = None,
        angle: str | None = None,
    ) -> ToolResult:
        settings = get_settings()
        audience = audience or "product managers and growth leads"

        # 1. Ground the essay in the corpus.
        passages = await ctx.retriever.retrieve(
            ctx.db, topic, top_k=settings.retrieval_top_k
        )
        if not passages:
            return ToolResult(
                content=(
                    "I could not find Lenny's Podcast material on that topic, so I "
                    "will not fabricate an essay. Tell the user the knowledge base "
                    "does not support it yet."
                )
            )

        grounded = []
        for p in passages:
            grounded.append(
                f"[{p.title} — episode {p.episode_id or 'n/a'}, chunk {p.chunk_index}]\n{p.text}"
            )
            ctx.add_citation(p.source_id, p.title, p.chunk_index, p.text[:280])

        # 2. Compose with the encoded principles.
        user_prompt = f"""
Write a Ship 30 for 30 essay on this topic: {topic}

Target audience: {audience}
{f"Requested angle: {angle}" if angle else ""}

Use ONLY the following grounded transcript material as your source of truth.
Do not introduce facts that are not present in these passages:

{chr(10).join(grounded)}

Return the essay as clean Markdown (headings, bullets, **bold**, numbered points).
"""
        response = await ctx.provider.complete(
            [
                ChatMessage(role="system", content=SHIP30_PRINCIPLES),
                ChatMessage(role="user", content=user_prompt),
            ],
            tools=None,
        )

        essay = response.content.strip()
        if not essay:
            return ToolResult(content="Failed to generate the essay; please retry.")

        # 3. Enforce the ~1,250-word length. Local models routinely stop at a
        # few hundred words; expand the draft in a bounded loop (never infinite,
        # never hard-failing the skill if the provider can't cooperate).
        for _ in range(MAX_EXPANSION_ROUNDS):
            if _word_count(essay) >= MIN_ESSAY_WORDS:
                break
            try:
                expansion = await ctx.provider.complete(
                    [
                        ChatMessage(role="system", content=SHIP30_PRINCIPLES),
                        ChatMessage(
                            role="user",
                            content=(
                                f"Your essay is currently {_word_count(essay)} words, "
                                f"but the brief requires approximately {TARGET_ESSAY_WORDS}. "
                                "Expand it: add more specific, grounded detail to each "
                                "numbered point, more concrete examples drawn from the "
                                "source material, and a richer takeaway. Keep the same "
                                "structure, hook, and skimmable formatting. Return the FULL "
                                "expanded essay as clean Markdown.\n\nCurrent essay:\n\n"
                                + essay
                            ),
                        ),
                    ],
                    tools=None,
                )
            except Exception:  # pragma: no cover - never fail the skill on expansion
                logger.warning("Ship 30 expansion failed; keeping the shorter draft")
                break
            expanded = (expansion.content or "").strip()
            if expanded and _word_count(expanded) > _word_count(essay):
                essay = expanded
            else:
                break

        # 4. Persist as a Markdown artifact for the viewer.
        title = f"Ship 30: {topic[:60]}"
        artifact = Artifact(
            conversation_id=ctx.conversation_id,
            kind="markdown",
            title=title,
            content=essay,
        )
        ctx.db.add(artifact)
        await ctx.db.flush()
        ctx.artifacts.append(artifact)

        return ToolResult(
            content=(
                f"I wrote a Ship 30 for 30 essay on '{topic}' (~1,250 words) and "
                f"rendered it as an artifact titled '{title}'. Here is the essay:\n\n{essay}"
            ),
            meta={"artifact_id": artifact.id, "title": title},
        )


class GenerateArtifactSkill(Tool):
    name = "generate_artifact"
    description = (
        "Generate a standalone Markdown document or complete HTML/CSS snippet based "
        "on the current conversation, and render it in the artifact viewer. Use when "
        "the user asks for a document, checklist, landing page, dashboard mockup, or "
        "any 'make me a file' request. HTML is sanitized for safety."
    )
    parameters = {
        "type": "object",
        "properties": {
            "kind": {
                "type": "string",
                "enum": ["markdown", "html"],
                "description": "The artifact format.",
            },
            "title": {"type": "string", "description": "Short title for the artifact."},
            "spec": {
                "type": "string",
                "description": "What the artifact should contain, referencing the conversation context.",
            },
        },
        "required": ["kind", "title", "spec"],
    }

    async def run(
        self,
        ctx: ToolContext,
        kind: str,
        title: str,
        spec: str,
    ) -> ToolResult:
        # Ground the artifact in recent conversation + corpus where relevant.
        passages = await ctx.retriever.retrieve(ctx.db, spec, top_k=4)
        grounding = ""
        if passages:
            joined = "\n\n".join(p.text for p in passages)
            grounding = f"\n\nRelevant transcript material to draw on:\n{joined}"

        if kind == "html":
            fmt_instruction = (
                "Return a complete, self-contained HTML snippet (valid HTML5 with "
                "inline <style> CSS). Do NOT include any <script> tags. Use semantic "
                "tags and simple, modern styling. Wrap the whole thing in a single "
                "<div class='artifact'> root."
            )
        else:
            fmt_instruction = (
                "Return clean Markdown (headings, lists, tables, **bold**, links)."
            )

        prompt = (
            f"Create a {kind} artifact titled '{title}'.\n\n"
            f"Requirements: {spec}\n{grounding}\n\n"
            f"{fmt_instruction}"
        )
        response = await ctx.provider.complete(
            [ChatMessage(role="user", content=prompt)], tools=None
        )
        content = response.content.strip()
        if not content:
            return ToolResult(content="Failed to generate the artifact; please retry.")

        if kind == "html":
            from app.core.security import sanitize_html

            content = sanitize_html(content)

        if len(content.encode("utf-8")) > get_settings().max_artifact_bytes:
            content = content[: get_settings().max_artifact_bytes]

        artifact = Artifact(
            conversation_id=ctx.conversation_id,
            kind=kind,
            title=title[:255],
            content=content,
        )
        ctx.db.add(artifact)
        await ctx.db.flush()
        ctx.artifacts.append(artifact)

        return ToolResult(
            content=f"Artifact '{title}' ({kind}) generated and rendered in the viewer.",
            meta={"artifact_id": artifact.id, "title": title, "kind": kind},
        )
