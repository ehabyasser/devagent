"""
agents/base_agent.py

Defines the Agent Loop contract.

The loop has five stages:
  1. UNDERSTAND  — Parse and validate the user's intent and inputs.
  2. PLAN        — Decide which tools to call and in what order.
  3. TOOL_CALL   — Execute tools (Jira fetch, diff parse, secret scan).
  4. VALIDATE    — Check tool outputs for errors, empty results, or anomalies.
  5. RESPOND     — Build a structured prompt, call the LLM, parse and return output.

This is NOT a ReAct loop yet (V2 scope). V1 is a single-shot plan-and-execute
loop. This keeps latency low and outputs deterministic.

Tradeoff: ReAct / tool-calling loops are more flexible but add 2-4x latency
and make JSON output harder to guarantee. For two well-defined tasks, a
single-shot approach with a strongly typed system prompt is more reliable.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, AsyncIterator, Optional

from backend.llm.base_llm import BaseLLM


class LoopStage(str, Enum):
    UNDERSTAND = "understand"
    PLAN = "plan"
    TOOL_CALL = "tool_call"
    VALIDATE = "validate"
    RESPOND = "respond"


@dataclass
class AgentContext:
    """Carries state through the agent loop."""
    raw_input: dict[str, Any]
    stage: LoopStage = LoopStage.UNDERSTAND
    tool_outputs: Optional[dict[str, Any]] = None
    error: Optional[str] = None


class BaseAgent(ABC):
    """
    Abstract agent. Subclasses implement each stage.
    The run() method orchestrates the loop and enforces stage ordering.
    """

    def __init__(self, llm: BaseLLM) -> None:
        self.llm = llm

    async def run(self, raw_input: dict[str, Any]) -> dict[str, Any]:
        """
        Execute the full agent loop.

        Returns a dict with either 'result' (success) or 'error' (failure).
        The caller (the API router) is responsible for HTTP status codes.
        """
        ctx = AgentContext(raw_input=raw_input)

        try:
            # ── 1. UNDERSTAND ──────────────────────────────────────────────
            ctx.stage = LoopStage.UNDERSTAND
            understood = await self.understand(ctx)

            # ── 2. PLAN ────────────────────────────────────────────────────
            ctx.stage = LoopStage.PLAN
            plan = await self.plan(understood)

            # ── 3. TOOL CALL ───────────────────────────────────────────────
            ctx.stage = LoopStage.TOOL_CALL
            tool_outputs = await self.call_tools(plan)
            ctx.tool_outputs = tool_outputs

            # ── 4. VALIDATE ────────────────────────────────────────────────
            ctx.stage = LoopStage.VALIDATE
            await self.validate(tool_outputs)

            # ── 5. RESPOND ─────────────────────────────────────────────────
            ctx.stage = LoopStage.RESPOND
            result = await self.respond(tool_outputs)

            return {"result": result, "stage_completed": ctx.stage}

        except Exception as exc:
            ctx.error = str(exc)
            return {
                "error": str(exc),
                "stage_failed": ctx.stage,
            }

    # ── Abstract stage methods ─────────────────────────────────────────────────

    @abstractmethod
    async def understand(self, ctx: AgentContext) -> dict[str, Any]:
        """Parse and validate raw input. Return a normalised input dict."""
        ...

    @abstractmethod
    async def plan(self, understood: dict[str, Any]) -> dict[str, Any]:
        """Decide which tools to call and with what parameters."""
        ...

    @abstractmethod
    async def call_tools(self, plan: dict[str, Any]) -> dict[str, Any]:
        """Execute tools; return their combined output."""
        ...

    @abstractmethod
    async def validate(self, tool_outputs: dict[str, Any]) -> None:
        """Inspect tool outputs. Raise ValueError if something is wrong."""
        ...

    @abstractmethod
    async def respond(self, tool_outputs: dict[str, Any]) -> dict[str, Any]:
        """Build the LLM prompt, call the model, parse and return output."""
        ...
