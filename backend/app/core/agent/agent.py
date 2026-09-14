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
from dataclasses import dataclass, field

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


@dataclass
class AgentResult:
    content: str
    grounded: bool = False
    tool_trace: list[str] = field(default_factory=list)


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
        messages = [ChatMessage(role="system", content=SYSTEM_PROMPT), *history]
        tool_specs = [t.spec() for t in self.tools]
        trace: list[str] = []

        for _ in range(MAX_ITERATIONS):
            response = await self.provider.complete(messages, tools=tool_specs)

            if response.tool_calls:
                trace.extend(tc.name for tc in response.tool_calls)
                messages.append(
                    ChatMessage(
                        role="assistant",
                        content=response.content,
                        tool_calls=response.tool_calls,
                    )
                )
                for call in response.tool_calls:
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

            return AgentResult(
                content=response.content or "(empty response)",
                grounded=bool(trace and "search_transcripts" in trace),
                tool_trace=trace,
            )

        return AgentResult(
            content=(
                "I reached the maximum number of tool steps while answering this. "
                "Please ask again with a narrower question."
            ),
            grounded=bool(trace and "search_transcripts" in trace),
            tool_trace=trace,
        )
