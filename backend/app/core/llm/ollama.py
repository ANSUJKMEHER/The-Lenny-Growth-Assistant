"""Ollama provider (local — mandatory for the demo).

Talks to Ollama's native ``/api/chat`` endpoint, which supports tool calling.
No API key is required; the only prerequisite is a running Ollama server with
the configured model pulled. This is the default provider so the submission
runs end-to-end on a laptop with no cloud credentials.
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

logger = logging.getLogger("app.llm.ollama")


class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(self, base_url: str, model: str, timeout: float = 120.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    # -- helpers ------------------------------------------------------------ #
    def _system_prompt(self, messages: list[ChatMessage]) -> str | None:
        parts = [m.content for m in messages if m.role == "system"]
        return "\n\n".join(parts) if parts else None

    def _to_ollama(self, messages: list[ChatMessage]) -> list[dict]:
        out: list[dict] = []
        for m in messages:
            if m.role == "system":
                continue  # folded into the top-level `system` field
            if m.role == "tool":
                out.append(
                    {"role": "tool", "content": m.content, "tool_name": m.name or ""}
                )
                continue
            d: dict = {"role": m.role, "content": m.content}
            if m.tool_calls:
                d["tool_calls"] = [
                    {
                        "function": {
                            "name": tc.name,
                            "arguments": tc.arguments,  # native dict form
                        }
                    }
                    for tc in m.tool_calls
                ]
            out.append(d)
        return out

    def _to_tools(self, tools: list[ToolSpec] | None) -> list[dict] | None:
        if not tools:
            return None
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in tools
        ]

    # -- main --------------------------------------------------------------- #
    async def complete(
        self, messages: list[ChatMessage], tools: list[ToolSpec] | None = None
    ) -> LLMResponse:
        payload: dict = {
            "model": self.model,
            "messages": self._to_ollama(messages),
            "stream": False,
            "options": {"temperature": 0.2},
        }
        system = self._system_prompt(messages)
        if system:
            payload["system"] = system
        if tools:
            payload["tools"] = self._to_tools(tools)

        url = f"{self.base_url}/api/chat"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(url, json=payload)
        except httpx.TimeoutException as exc:
            raise ProviderError(f"Ollama timed out after {self.timeout}s") from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"Ollama unreachable at {self.base_url}: {exc}") from exc

        if resp.status_code >= 400:
            raise ProviderError(f"Ollama HTTP {resp.status_code}: {resp.text[:300]}")

        try:
            data = resp.json()
        except json.JSONDecodeError as exc:  # pragma: no cover
            raise ProviderError("Ollama returned non-JSON response") from exc

        message = data.get("message") or {}
        content = message.get("content") or ""

        tool_calls: list[ToolCall] = []
        for tc in message.get("tool_calls") or []:
            fn = tc.get("function") or {}
            args = fn.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            tool_calls.append(
                ToolCall(
                    id=tc.get("id") or f"call_{len(tool_calls)}",
                    name=fn.get("name") or "",
                    arguments=args,
                )
            )

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=data.get("done_reason") or "stop",
            raw=data,
        )


class OllamaEmbedder:
    """Text embedding via Ollama's ``/api/embeddings`` endpoint."""

    def __init__(self, base_url: str, model: str, timeout: float = 120.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    async def embed(self, text: str) -> list[float]:
        url = f"{self.base_url}/api/embeddings"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(url, json={"model": self.model, "prompt": text})
        except httpx.HTTPError as exc:
            raise ProviderError(f"Ollama embeddings unavailable: {exc}") from exc
        if resp.status_code >= 400:
            raise ProviderError(f"Ollama embeddings HTTP {resp.status_code}")
        data = resp.json()
        return data.get("embedding") or []
