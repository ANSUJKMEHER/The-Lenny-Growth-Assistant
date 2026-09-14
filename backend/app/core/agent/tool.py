"""Tool (and Skill) base classes.

A Tool is the atomic unit the agent can route to; a Skill is a higher-level,
domain-specific capability (e.g. "Ship 30 for 30 essay") that composes its own
prompting and may itself call retrieval or the LLM. Skills are exposed to the
router as tools, keeping a single, uniform tool-calling contract.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from app.core.agent.context import ToolContext
from app.core.llm.base import ToolSpec


@dataclass
class ToolResult:
    """String payload returned to the model after tool execution."""

    content: str
    # Optional structured hints used by the endpoint (e.g. artifact ids).
    meta: dict[str, Any] | None = None


class Tool(ABC):
    """Base for every tool/skill the agent can invoke."""

    name: str = "tool"
    description: str = ""
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    def spec(self) -> ToolSpec:
        return ToolSpec(name=self.name, description=self.description, parameters=self.parameters)

    @abstractmethod
    async def run(self, ctx: ToolContext, **kwargs: Any) -> ToolResult:
        """Execute the tool. ``kwargs`` come from model-provided arguments."""
