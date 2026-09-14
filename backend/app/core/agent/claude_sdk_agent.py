"""Optional Claude Agent SDK integration (Anthropic path only).

The brief names the Anthropic Claude Agent SDK (and Pi Coding Agent) as the
agent-layer runtime. We integrate the official SDK as an *optional* runtime that
takes over the orchestration loop when the Anthropic provider is active and the
SDK (plus the Claude Code CLI it spawns) is installed.

When the SDK/CLI is absent — or the demo runs on local Ollama — the app
transparently uses the built-in provider-agnostic loop in ``agent.py``. The two
runtimes share the exact same tools/skills and ``ToolContext``, so routing,
grounding, citations, and artifact behavior are identical; only the orchestration
engine differs.

Runtime selection is controlled by ``AGENT_RUNTIME``:
  - ``auto``      (default) use the SDK when possible, else the built-in loop.
  - ``claude_sdk`` require the SDK (error if unavailable).
  - ``builtin``   always use the built-in loop.
"""
from __future__ import annotations

import logging
import shutil
from typing import Any

from app.config import get_settings
from app.core.agent.agent import Agent, AgentResult, SYSTEM_PROMPT, build_default_tools
from app.core.agent.context import ToolContext
from app.core.llm.base import ChatMessage, ProviderError

logger = logging.getLogger("app.agent.claude_sdk")


class SDKUnavailableError(RuntimeError):
    """Raised when the SDK (or its CLI) is required but not usable."""


def sdk_importable() -> bool:
    """Whether the ``claude-agent-sdk`` package is installed."""
    try:
        import claude_agent_sdk  # noqa: F401
        return True
    except ImportError:
        return False


def cli_available() -> bool:
    """Whether the Claude Code CLI the SDK spawns is discoverable."""
    settings = get_settings()
    if settings.claude_cli_path:
        return True
    return shutil.which("claude") is not None


def can_use_claude_sdk() -> bool:
    return sdk_importable() and cli_available()


def select_agent(provider: Any):
    """Return the agent runtime to drive this request.

    Both return types implement ``async run(ctx, history) -> AgentResult``.
    """
    settings = get_settings()
    runtime = settings.agent_runtime.lower().strip()

    if runtime == "builtin" or provider.name != "anthropic":
        return Agent(provider)

    if runtime == "claude_sdk":
        if not sdk_importable():
            raise SDKUnavailableError(
                "AGENT_RUNTIME=claude_sdk but the `claude-agent-sdk` package is "
                "not installed. Run: pip install 'claude-agent-sdk'."
            )
        if not cli_available():
            raise SDKUnavailableError(
                "AGENT_RUNTIME=claude_sdk but the Claude Code CLI (`claude`) was "
                "not found on PATH. Install it or set CLAUDE_CLI_PATH."
            )
        logger.info("Using the Claude Agent SDK for the Anthropic path")
        return ClaudeSDKAgent(provider)

    # runtime == "auto"
    if can_use_claude_sdk():
        logger.info("Claude Agent SDK detected; using it for the Anthropic path")
        return ClaudeSDKAgent(provider)

    logger.info(
        "Claude Agent SDK/CLI not available; using the built-in agent loop "
        "(Anthropic provider via HTTP)"
    )
    return Agent(provider)


class ClaudeSDKAgent:
    """Agent loop driven by the official Anthropic Claude Agent SDK.

    Our tools/skills are exposed to the SDK as an **in-process MCP server**, so
    the SDK's model decides when to call ``search_transcripts``,
    ``write_ship30_essay``, etc. — the same routing the built-in loop performs.
    """

    def __init__(self, provider: Any) -> None:
        self.provider = provider  # an AnthropicProvider instance

    async def run(self, ctx: ToolContext, history: list[ChatMessage]) -> AgentResult:
        from claude_agent_sdk import (  # local import keeps this optional
            AssistantMessage,
            ClaudeAgentOptions,
            ResultMessage,
            TextBlock,
            ToolUseBlock,
            create_sdk_mcp_server,
            query,
            tool,
        )

        tools = build_default_tools()

        # Adapt our Tool/Skill objects to SDK MCP tools. Each handler receives a
        # dict of validated arguments and returns an MCP CallToolResult dict.
        sdk_tools: list[Any] = []
        for t in tools:

            @tool(t.name, t.description, t.parameters)
            async def handler(args: dict[str, Any], _t: Any = t) -> dict[str, Any]:
                try:
                    result = await _t.run(ctx, **args)
                except Exception as exc:  # tools must not crash the SDK run
                    logger.exception("SDK tool %s failed", _t.name)
                    return {
                        "content": [{"type": "text", "text": f"Error: {exc}"}],
                        "is_error": True,
                    }
                return {"content": [{"type": "text", "text": result.content}]}

            sdk_tools.append(handler)

        server = create_sdk_mcp_server(
            name="lenny-growth-tools",
            version="1.0.0",
            tools=sdk_tools,
        )

        options = ClaudeAgentOptions(
            system_prompt=SYSTEM_PROMPT,
            mcp_servers={"lenny": server},
            # Our tools are in-process and safe; no interactive prompts wanted
            # inside a web request, and no filesystem/shell tools exposed.
            permission_mode="bypassPermissions",
            allowed_tools=[],
            model=self.provider.model,
            max_turns=12,
            # Deterministic: ignore the evaluator's local ~/.claude settings.
            setting_sources=[],
            skills=[],
            cli_path=get_settings().claude_cli_path or None,
            env={"ANTHROPIC_API_KEY": self.provider.api_key},
        )

        prompt = self._history_to_prompt(history)

        text_parts: list[str] = []
        trace: list[str] = []
        result_msg: Any = None
        try:
            async for message in query(prompt=prompt, options=options):
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            text_parts.append(block.text)
                        elif isinstance(block, ToolUseBlock):
                            trace.append(block.name)
                elif isinstance(message, ResultMessage):
                    result_msg = message
        except Exception as exc:
            raise ProviderError(f"Claude Agent SDK failure: {exc}") from exc

        if result_msg is not None and getattr(result_msg, "is_error", False):
            raise ProviderError(
                f"Claude Agent SDK returned an error: "
                f"{getattr(result_msg, 'result', '') or 'unknown error'}"
            )

        content = "\n".join(p.strip() for p in text_parts if p.strip())
        if not content and result_msg is not None:
            content = getattr(result_msg, "result", "") or ""

        return AgentResult(
            content=content or "(empty response)",
            grounded=bool(ctx.citations),
            tool_trace=trace,
        )

    @staticmethod
    def _history_to_prompt(history: list[ChatMessage]) -> str:
        lines: list[str] = []
        for m in history:
            if m.role == "user":
                lines.append(f"User: {m.content}")
            elif m.role == "assistant":
                lines.append(f"Assistant: {m.content}")
        return "\n\n".join(lines)
