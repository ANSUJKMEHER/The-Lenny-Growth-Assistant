"""Provider-agnostic LLM interface.

All three providers (Ollama, Anthropic, OpenAI) are normalised onto a single
message/response contract so the agent layer never cares which backend is in
use. The factory in :mod:`app.core.llm.factory` picks (and can fall back
between) providers based on configuration and runtime availability.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


class ProviderError(RuntimeError):
    """Raised when a provider cannot fulfil a request (network, auth, timeout)."""


@dataclass
class ToolSpec:
    """A callable tool exposed to the model (function-calling schema)."""

    name: str
    description: str
    parameters: dict[str, Any]


@dataclass
class ToolCall:
    """A tool invocation requested by the model."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ChatMessage:
    """Normalised chat message used across providers."""

    role: str  # "system" | "user" | "assistant" | "tool"
    content: str
    tool_call_id: str | None = None  # required when role == "tool"
    name: str | None = None  # tool name when role == "tool"
    tool_calls: list[ToolCall] | None = None  # when role == "assistant"

    def to_openai_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.tool_call_id is not None:
            d["tool_call_id"] = self.tool_call_id
        if self.tool_calls:
            d["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.name, "arguments": _json_dumps(tc.arguments)},
                }
                for tc in self.tool_calls
            ]
        return d


@dataclass
class LLMResponse:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str = "stop"
    raw: Any = None


def _json_dumps(obj: Any) -> str:
    import json

    return json.dumps(obj, ensure_ascii=False)


class LLMProvider(ABC):
    """Abstract base for a chat-completion provider with tool calling."""

    name: str = "base"
    model: str = ""

    @abstractmethod
    async def complete(
        self, messages: list[ChatMessage], tools: list[ToolSpec] | None = None
    ) -> LLMResponse:
        """Run a single completion with optional tools."""

    async def healthcheck(self) -> tuple[bool, str | None]:
        """Return (available, reason_if_not)."""
        try:
            # A tiny no-tool completion proves the endpoint + model work.
            await self.complete(
                [ChatMessage(role="user", content="ping")], tools=None
            )
            return True, None
        except ProviderError as exc:  # pragma: no cover - depends on env
            return False, str(exc)
        except Exception as exc:  # pragma: no cover
            return False, f"{type(exc).__name__}: {exc}"
