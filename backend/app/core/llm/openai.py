"""OpenAI provider (cloud, and any OpenAI-compatible endpoint).

Uses the Chat Completions API with the parallel function-calling contract.
Requires ``OPENAI_API_KEY``; ``OPENAI_BASE_URL`` can point at any compatible
endpoint (Azure, Together, etc.).
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

logger = logging.getLogger("app.llm.openai")


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self, api_key: str, model: str, base_url: str) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")

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

    async def complete(
        self, messages: list[ChatMessage], tools: list[ToolSpec] | None = None
    ) -> LLMResponse:
        payload: dict = {
            "model": self.model,
            "messages": [m.to_openai_dict() for m in messages],
            "temperature": 0.2,
        }
        if tools:
            payload["tools"] = self._to_tools(tools)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self.base_url}/chat/completions"
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(url, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            raise ProviderError(f"OpenAI unreachable: {exc}") from exc

        if resp.status_code == 401:
            raise ProviderError("OpenAI API key missing or invalid")
        if resp.status_code >= 400:
            raise ProviderError(f"OpenAI HTTP {resp.status_code}: {resp.text[:300]}")

        data = resp.json()
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}

        tool_calls: list[ToolCall] = []
        for tc in message.get("tool_calls") or []:
            fn = tc.get("function") or {}
            args = fn.get("arguments") or "{}"
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            tool_calls.append(
                ToolCall(id=tc.get("id", ""), name=fn.get("name", ""), arguments=args)
            )

        return LLMResponse(
            content=message.get("content") or "",
            tool_calls=tool_calls,
            finish_reason=choice.get("finish_reason") or "stop",
            raw=data,
        )

    async def healthcheck(self) -> tuple[bool, str | None]:
        """Cheap probe: a single-token completion instead of a full reply."""
        import httpx as _httpx

        try:
            async with _httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    json={
                        "model": self.model,
                        "messages": [{"role": "user", "content": "ping"}],
                        "max_tokens": 1,
                    },
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                )
        except _httpx.HTTPError as exc:
            return False, f"OpenAI unreachable: {exc}"
        if resp.status_code == 401:
            return False, "OpenAI API key missing or invalid"
        if resp.status_code >= 400:
            return False, f"OpenAI HTTP {resp.status_code}: {resp.text[:200]}"
        return True, None
