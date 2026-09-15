"""Agent orchestration: the tool-calling loop that routes work to skills.

The agent implements the same turn-based tool-use contract as the Claude Agent
SDK / Pi Coding Agent, but against our provider-agnostic LLM layer so it works
identically with Ollama (local), Anthropic, or OpenAI backends.

Loop:
1. Send conversation + system prompt + tool schemas to the model.
2. If the model requests tool calls, execute them (search, Ship 30, artifact),
   append the results, and loop.
3. When the model returns a plain answer, stop and return it.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from app.config import get_settings
from app.core.agent.context import ToolContext
from app.core.agent.tool import Tool
from app.core.agent.tools import ListSourcesTool, SearchTranscriptsTool
from app.core.agent.skills.ship30 import GenerateArtifactSkill, Ship30EssaySkill
from app.core.llm.base import ChatMessage, LLMProvider, ToolCall

logger = logging.getLogger("app.agent")

MAX_ITERATIONS = 8

SYSTEM_PROMPT = """\
You are "The Lenny Growth Assistant", an internal assistant for a product and
growth team, grounded strictly in Lenny's Podcast transcripts.

SCOPE (non-negotiable):
- You ONLY answer product management and growth questions using Lenny's
  Podcast material. You are NOT a general-purpose assistant, a coding
  assistant, or a chatbot that writes software.
- If the user asks for something outside this scope — e.g. "write a tic-tac-toe
  game", "generate Python code", math problems, or unrelated trivia — decline
  briefly, explain what you DO help with, and offer to answer a product/growth
  question instead. Never generate code, programs, or ungrounded content.

GROUNDING RULES (non-negotiable):
- Answer only from the indexed transcript material. Use search_transcripts to
  retrieve evidence before answering anything substantive.
- When the material does not support an answer, say so plainly and tell the
  user what the knowledge base does and does not cover. Never invent facts,
  episode numbers, quotes, or statistics.
- Prefer to cite the source (episode title) when you use a passage.

TOOL ROUTING:
- search_transcripts  -> any question about product management, growth,
  retention, hiring, strategy, or anything Lenny has discussed.
- list_sources        -> when the user asks what's in the knowledge base.
- write_ship30_essay  -> when the user wants a Ship 30 for 30-style essay or a
  polished, shareable written piece.
- generate_artifact    -> when the user wants a standalone document, checklist,
  landing page, or HTML/CSS snippet rendered in the viewer.

STYLE:
- Be concise and specific. Use short paragraphs, bullets, and **bold** for
  emphasis. Answer follow-up questions using the conversation context.
"""

# Deterministic scope guard: local models sometimes ignore the system prompt and
# answer off-topic requests anyway. This catches the most obvious "write code /
# build a game" requests before the model is invoked, so the assistant reliably
# stays on-brand and returns instantly instead of generating an off-topic answer.
def _normalize(text: str) -> str:
    """Lowercase and collapse every non-alphanumeric run to a single space.

    'tic-tac-toe', 'tic.tac.toe' and 'tic tac toe' then normalise identically,
    which makes the scope guard robust to punctuation instead of enumerating
    every hyphen/dot/spacing variant.
    """
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


_GAME_NAMES = re.compile(
    r"\b(tic tac toe|hangman|snake game|rock paper scissors|sudoku|chess|pong|"
    r"tetris|minesweeper|wordle|guess the number|naughts and crosses|"
    r"connect four|checkers|battleship|blackjack|poker|pacman|breakout|"
    r"space invaders)\b"
)
_OFF_TOPIC_VERBS = re.compile(
    r"\b(write|generate|create|make|code|build|implement|program)\b"
)
# Words that unambiguously signal general software/coding work. Deliberately
# excludes "html"/"css"/"website"/"checklist"/"landing page" because those are
# legitimate artifact requests handled by generate_artifact.
_OFF_TOPIC_OBJECTS = re.compile(
    r"\b(game|code|program|programming|script|function|class|algorithm|bot|software|"
    r"repo|database|calculator|puzzle|python|javascript|java|ruby|golang|rust|sql|"
    r"node js|nodejs|typescript|react js|reactjs|react native|react component|"
    r"fibonacci|binary search|sorting algorithm)\b"
)

# A fenced code block (```language) is a strong signal the model produced raw
# code as a direct answer rather than a grounded response.
_CODE_FENCE = re.compile(r"```[a-zA-Z0-9+#.\-]*\s*\n")

_REFUSAL = (
    "I'm the **Lenny Growth Assistant** — I answer product and growth questions "
    "grounded in Lenny's Podcast transcripts, so I can't write code, games, or "
    "general software.\n\n"
    "Try me with something like:\n"
    "- What does Lenny say about retention and activation?\n"
    "- How do I know I've found product-market fit?\n"
    "- Write a Ship 30 for 30 essay on positioning.\n"
    "- Make an HTML checklist for improving onboarding."
)


def off_topic_response(text: str) -> str | None:
    """Return a polite refusal for clearly out-of-scope requests, else ``None``."""
    t = _normalize(text)
    if not t:
        return None
    if _GAME_NAMES.search(t):
        return _REFUSAL
    if _OFF_TOPIC_VERBS.search(t) and _OFF_TOPIC_OBJECTS.search(t):
        return _REFUSAL
    return None


_GREETING_RE = re.compile(
    r"^(hi|hello|hey|yo|sup|thanks|thank you|good (morning|afternoon|evening)|"
    r"ok|okay|bye|goodbye)\b",
    re.IGNORECASE,
)


def _is_substantive(text: str) -> bool:
    """True for a real question that should be grounded; False for chit-chat."""
    t = (text or "").strip()
    if not t:
        return False
    return _GREETING_RE.match(t) is None


def _format_passages(results) -> str:
    """Render retrieved chunks as a readable, numbered block for the model."""
    parts = []
    for i, r in enumerate(results, 1):
        src = r.title or "Lenny's Podcast"
        if getattr(r, "episode_id", None):
            src += f" (episode {r.episode_id})"
        if getattr(r, "speaker", None):
            src += f" — {r.speaker}"
        if getattr(r, "timestamp", None):
            src += f" @ {r.timestamp}"
        parts.append(f"[{i}] {src}\n{r.text.strip()}")
    return "\n\n".join(parts)


def _title_signature(title: str | None) -> str:
    """Normalized title used to detect whether an answer cited a source."""
    cleaned = re.sub(r"\[[^\]]*\]", " ", title or "")
    return _normalize(cleaned)


def _mentions_source(content: str, citations) -> bool:
    """True if ``content`` references at least one retrieved source."""
    if not content:
        return False
    for i in range(1, len(citations) + 1):
        if f"[{i}]" in content:
            return True
    norm = _normalize(content)
    for c in citations:
        sig = _title_signature(getattr(c, "title", None))
        if sig and sig in norm:
            return True
    return False


def _build_grounded_answer(results) -> str:
    """Deterministic, verbatim, source-tagged answer used when the model's
    synthesis is generic or otherwise fails to cite the retrieved material."""
    lines = ["Here's what Lenny's Podcast says about that:\n"]
    for r in results[:3]:
        src = r.title or "Lenny's Podcast"
        if getattr(r, "episode_id", None):
            src += f" (episode {r.episode_id})"
        meta = ""
        if getattr(r, "speaker", None):
            meta += f" — {r.speaker}"
        if getattr(r, "timestamp", None):
            meta += f" @ {r.timestamp}"
        text = r.text.strip()
        if len(text) > 600:
            text = text[:600].rstrip() + "…"
        lines.append(f"**{src}**{meta}:\n> {text}\n")
    return "\n".join(lines).strip()


@dataclass
class AgentResult:
    content: str
    grounded: bool = False
    tool_trace: list[str] = field(default_factory=list)


@dataclass
class AgentEvent:
    """A streaming increment emitted by the agent loop.

    ``kind`` is one of ``token`` (answer text), ``tool`` (a tool was invoked),
    or ``done`` (terminal, carries the final :class:`AgentResult`).
    """

    kind: str
    data: str = ""
    result: AgentResult | None = None


def build_default_tools() -> list[Tool]:
    return [
        SearchTranscriptsTool(),
        ListSourcesTool(),
        Ship30EssaySkill(),
        GenerateArtifactSkill(),
    ]


class Agent:
    def __init__(
        self, provider: LLMProvider, tools: list[Tool] | None = None
    ) -> None:
        self.provider = provider
        self.tools = tools or build_default_tools()
        self._by_name = {t.name: t for t in self.tools}

    async def _execute(self, ctx: ToolContext, call: ToolCall) -> str:
        tool = self._by_name.get(call.name)
        if tool is None:
            return f"Error: unknown tool '{call.name}'."
        try:
            result = await tool.run(ctx, **call.arguments)
            return result.content
        except Exception as exc:  # tools must never crash the loop
            logger.exception("Tool %s failed", call.name)
            return f"Error running {call.name}: {type(exc).__name__}: {exc}"

    async def run(
        self,
        ctx: ToolContext,
        history: list[ChatMessage],
    ) -> AgentResult:
        """Run the agent loop and return the final result (non-streaming)."""
        result: AgentResult | None = None
        async for ev in self.run_stream(ctx, history):
            if ev.kind == "done" and ev.result is not None:
                result = ev.result
        return result or AgentResult(content="(empty response)")

    async def run_stream(
        self,
        ctx: ToolContext,
        history: list[ChatMessage],
    ):
        """Run the agent loop, yielding :class:`AgentEvent` increments.

        Identical tool-calling logic to :meth:`run`, except the final answer is
        streamed token-by-token (where the provider supports it) and tool
        invocations are surfaced as ``tool`` events for client progress.
        """
        # Short-circuit clearly out-of-scope requests without a model call.
        last_user = next(
            (m.content for m in reversed(history) if m.role == "user"), ""
        )
        refusal = off_topic_response(last_user)
        if refusal:
            yield AgentEvent(kind="token", data=refusal)
            yield AgentEvent(
                kind="done",
                result=AgentResult(content=refusal, grounded=False, tool_trace=[]),
            )
            return

        messages = [ChatMessage(role="system", content=SYSTEM_PROMPT), *history]
        tool_specs = [t.spec() for t in self.tools]
        trace: list[str] = []

        for _ in range(MAX_ITERATIONS):
            text_parts: list[str] = []
            tool_calls: list[ToolCall] = []

            async for chunk in self.provider.stream(messages, tools=tool_specs):
                if chunk.tool_calls:
                    tool_calls.extend(chunk.tool_calls)
                if chunk.text:
                    text_parts.append(chunk.text)
                    # Only stream answer text after a tool has already run (trace
                    # is non-empty). The first-pass answer is buffered because it
                    # may need force-grounding: if the model answered without
                    # searching we replace it with a grounded answer, and we don't
                    # want to have already streamed the generic text to the client.
                    if not chunk.tool_calls and not tool_calls and trace:
                        yield AgentEvent(kind="token", data=chunk.text)

            if tool_calls:
                trace.extend(tc.name for tc in tool_calls)
                messages.append(
                    ChatMessage(role="assistant", content="", tool_calls=tool_calls)
                )
                for call in tool_calls:
                    yield AgentEvent(kind="tool", data=call.name)
                    result = await self._execute(ctx, call)
                    messages.append(
                        ChatMessage(
                            role="tool",
                            content=result,
                            tool_call_id=call.id,
                            name=call.name,
                        )
                    )
                continue

            content = "".join(text_parts)
            retrieved = None

            # Defense in depth: if the model answered with a code block directly
            # (no tool was used), it ignored the scope guard. Swap in the branded
            # refusal instead of surfacing generated code.
            if not trace and _CODE_FENCE.search(content):
                yield AgentEvent(kind="token", data=_REFUSAL)
                yield AgentEvent(
                    kind="done",
                    result=AgentResult(content=_REFUSAL, grounded=False, tool_trace=[]),
                )
                return

            # ---- Grounding guarantee --------------------------------------
            # Local models often answer without searching, or search and then
            # ignore the passages and produce generic advice. We therefore
            # (1) retrieve deterministically for any substantive question the
            # model failed to ground, (2) re-answer on readable (non-JSON)
            # passages, and (3) fall back to a verbatim, source-tagged answer if
            # the model still won't cite a source. This makes grounding
            # independent of the model's tool-calling ability.
            searched = "search_transcripts" in trace
            if not searched and not ctx.citations and _is_substantive(last_user):
                retrieved = await ctx.retriever.retrieve(
                    ctx.db, last_user, top_k=get_settings().retrieval_top_k
                )
                if retrieved:
                    for r in retrieved:
                        ctx.add_citation(
                            r.source_id,
                            r.title,
                            r.chunk_index,
                            r.text[:280],
                            speaker=r.speaker,
                            timestamp=r.timestamp,
                            url=r.url,
                        )
                    yield AgentEvent(kind="tool", data="search_transcripts")
                    messages.append(ChatMessage(role="assistant", content=content))
                    messages.append(
                        ChatMessage(
                            role="user",
                            content=(
                                "Answer the user's original question using ONLY the "
                                "retrieved Lenny's Podcast passages below. Quote or closely "
                                "paraphrase them, name the episode and speaker, and tag each "
                                "point with its bracketed source number (e.g. [1], [2]). Do "
                                "not give generic advice, do not invent facts, and do not "
                                "answer from outside knowledge.\n\nRetrieved passages:\n"
                                + _format_passages(retrieved)
                            ),
                        )
                    )
                    grounded_parts: list[str] = []
                    async for chunk in self.provider.stream(messages, tools=None):
                        if chunk.text:
                            grounded_parts.append(chunk.text)
                    if grounded_parts:
                        content = "".join(grounded_parts)

            # If the model still produced an un-grounded answer despite having
            # retrieved material, substitute a verbatim, source-tagged answer so
            # the response is never generic fluff.
            if ctx.citations and not _mentions_source(content, ctx.citations):
                passages = retrieved
                if not passages:
                    passages = await ctx.retriever.retrieve(
                        ctx.db, last_user, top_k=get_settings().retrieval_top_k
                    )
                if passages:
                    content = _build_grounded_answer(passages)

            # The first-pass answer is buffered (not streamed) so the client never
            # shows an un-grounded draft. Emit the final content once now that the
            # grounding decision is made. (Answers that already streamed during a
            # post-tool pass are left untouched.)
            if not trace:
                yield AgentEvent(kind="token", data=content or "")

            yield AgentEvent(
                kind="done",
                result=AgentResult(
                    content=content or "(empty response)",
                    # Grounded means this turn actually attached source
                    # citations (retrieved + cited), not merely that a tool was
                    # invoked. Essay/artifact skills cite internally, so this is
                    # consistent across every tool path.
                    grounded=bool(ctx.citations),
                    tool_trace=trace,
                ),
            )
            return

        yield AgentEvent(
            kind="done",
            result=AgentResult(
                content=(
                    "I reached the maximum number of tool steps while answering this. "
                    "Please ask again with a narrower question."
                ),
                grounded=bool(ctx.citations),
                tool_trace=trace,
            ),
        )
