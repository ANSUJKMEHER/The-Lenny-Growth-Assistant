"""Anthropic provider (cloud).

Implemented against the Anthropic Messages API (``/v1/messages``) via httpx so
the app has no hard dependency on the official SDK. This is the same
tool-use contract the Claude Agent SDK drives; our agent loop consumes it
directly. Requires ``ANTHROPIC_API_KEY``.
"""
from __future__ import annotations

import json
import logging

import httpx

from app.core.llm.base import (
    ChatMessage,
    LLMProvider,
    LLMResponse,
    ProviderError,
    ToolCall,
    ToolSpec,
)

logger = logging.getLogger("app.llm.anthropic")

TOOL_INPUT_KEYS = ("input", "arguments", "parameters")


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(
        self, api_key: str, model: str, base_url: str = "https://api.anthropic.com/v1"
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")

    # -- conversion --------------------------------------------------------- #
    def _system_prompt(self, messages: list[ChatMessage]) -> str | None:
        parts = [m.content for m in messages if m.role == "system"]
        return "\n\n".join(parts) if parts else None

    def _to_anthropic(self, messages: list[ChatMessage]) -> list[dict]:
        out: list[dict] = []
        for m in messages:
            if m.role == "system":
                continue
            if m.role == "tool":
                out.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": m.tool_call_id,
                                "content": m.content,
                            }
                        ],
                    }
                )
                continue
            if m.role == "assistant" and m.tool_calls:
                blocks: list[dict] = []
                if m.content:
                    blocks.append({"type": "text", "text": m.content})
                for tc in m.tool_calls:
                    blocks.append(
                        {
                            "type": "tool_use",
                            "id": tc.id,
                            "name": tc.name,
                            "input": tc.arguments,
                        }
                    )
                out.append({"role": "assistant", "content": blocks})
                continue
            out.append({"role": m.role, "content": m.content})
        return out

    def _to_tools(self, tools: list[ToolSpec] | None) -> list[dict] | None:
        if not tools:
            return None
        return [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.parameters,
            }
            for t in tools
        ]

    # -- main --------------------------------------------------------------- #
    async def complete(
        self, messages: list[ChatMessage], tools: list[ToolSpec] | None = None
    ) -> LLMResponse:
        payload: dict = {
            "model": self.model,
            "messages": self._to_anthropic(messages),
            "max_tokens": 4096,
            "temperature": 0.2,
        }
        system = self._system_prompt(messages)
        if system:
            payload["system"] = system
        if tools:
            payload["tools"] = self._to_tools(tools)

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        url = f"{self.base_url}/messages"
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(url, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            raise ProviderError(f"Anthropic unreachable: {exc}") from exc

        if resp.status_code == 401:
            raise ProviderError("Anthropic API key missing or invalid")
        if resp.status_code >= 400:
            raise ProviderError(f"Anthropic HTTP {resp.status_code}: {resp.text[:300]}")

        data = resp.json()
        content_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        for block in data.get("content") or []:
            if block.get("type") == "text":
                content_parts.append(block.get("text", ""))
            elif block.get("type") == "tool_use":
                args = block.get("input") or {}
                tool_calls.append(
                    ToolCall(
                        id=block.get("id", ""), name=block.get("name", ""), arguments=args
                    )
                )

        return LLMResponse(
            content="\n".join(content_parts),
            tool_calls=tool_calls,
            finish_reason=data.get("stop_reason") or "stop",
            raw=data,
        )
