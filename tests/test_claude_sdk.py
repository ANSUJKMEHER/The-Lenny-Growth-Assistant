"""Agent runtime selection (built-in loop vs. optional Claude Agent SDK)."""
from app.core.agent.agent import Agent
from app.core.agent.claude_sdk_agent import (
    ClaudeSDKAgent,
    SDKUnavailableError,
    cli_available,
    sdk_importable,
    select_agent,
)
from app.core.llm.base import LLMProvider


class NamedProvider(LLMProvider):
    """Minimal provider stub carrying only the name used for routing."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.model = "stub"

    async def complete(self, messages, tools=None):
        raise NotImplementedError


def test_builtin_for_non_anthropic_provider():
    agent = select_agent(NamedProvider("ollama"))
    assert isinstance(agent, Agent)


def test_builtin_when_sdk_or_cli_unavailable(monkeypatch):
    monkeypatch.setattr("app.core.agent.claude_sdk_agent.sdk_importable", lambda: False)
    monkeypatch.setattr("app.core.agent.claude_sdk_agent.cli_available", lambda: False)
    agent = select_agent(NamedProvider("anthropic"))
    assert isinstance(agent, Agent)


def test_claude_sdk_used_when_available(monkeypatch):
    monkeypatch.setattr("app.core.agent.claude_sdk_agent.sdk_importable", lambda: True)
    monkeypatch.setattr("app.core.agent.claude_sdk_agent.cli_available", lambda: True)
    agent = select_agent(NamedProvider("anthropic"))
    assert isinstance(agent, ClaudeSDKAgent)


def test_claude_sdk_required_mode_errors_when_missing(monkeypatch):
    import pytest

    import app.core.agent.claude_sdk_agent as mod

    class FakeSettings:
        agent_runtime = "claude_sdk"
        claude_cli_path = ""

    monkeypatch.setattr(mod, "get_settings", lambda: FakeSettings())
    monkeypatch.setattr(mod, "sdk_importable", lambda: False)
    with pytest.raises(SDKUnavailableError):
        select_agent(NamedProvider("anthropic"))


def test_availability_probes_are_booleans():
    assert isinstance(sdk_importable(), bool)
    assert isinstance(cli_available(), bool)
