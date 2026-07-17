"""
agents/test_gen_agent.py

Test Case Generation Agent.

Understand → fetch Jira ticket (or use provided description)
Plan      → decide test categories based on issue type
Tool Call → fetch Jira ticket via REST API
Validate  → ensure description is non-empty
Respond   → prompt LLM with strict JSON schema, parse TestSuite
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from backend.agents.base_agent import BaseAgent, AgentContext
from backend.llm.base_llm import BaseLLM
from backend.schemas.test_case import TestSuite
from backend.tools.jira_tool import fetch_jira_ticket


_SYSTEM_PROMPT = """You are a senior QA engineer and testing strategist. 
Your job is to produce comprehensive, professional test cases from a software requirement.

Rules:
1. Return ONLY valid JSON that matches the provided schema — no markdown, no commentary.
2. Cover all four categories: happy_path, negative, boundary, regression.
3. Each test case must have at minimum 2 steps.
4. Be specific: use realistic data, not placeholders like "Enter valid data".
5. Priority P0 = crash / data loss risk. P1 = core flow. P2 = secondary. P3 = cosmetic.
6. If acceptance criteria are provided, derive test cases directly from them.
7. Regression cases should reference the type of bug they guard against.
8. Generate comprehensive test coverage: aim for 8–15 test cases covering all four categories proportionally. Do NOT artificially limit output — the goal is thorough coverage, not brevity.

Return a JSON object matching this TypeScript interface:
{
  ticket_id: string,
  ticket_summary: string,
  generated_at: string,   // ISO-8601
  model_used: string,
  total_cases: number,
  cases: Array<{
    id: string,            // TC-001, TC-002, ...
    title: string,
    category: "happy_path" | "negative" | "boundary" | "regression",
    priority: "P0" | "P1" | "P2" | "P3",
    preconditions: string[],
    steps: Array<{ step_number: number, action: string, expected_result: string }>,
    expected_outcome: string,
    tags: string[]
  }>,
  coverage_notes: string
}
"""


class TestGenAgent(BaseAgent):
    def __init__(self, llm: BaseLLM) -> None:
        super().__init__(llm)

    # ── 1. UNDERSTAND ──────────────────────────────────────────────────────────
    async def understand(self, ctx: AgentContext) -> dict[str, Any]:
        data = ctx.raw_input
        ticket_id: Optional[str] = data.get("ticket_id")
        manual_description: Optional[str] = data.get("description")
        pr_title: str = data.get("pr_title", "")

        if not ticket_id and not manual_description:
            raise ValueError(
                "Provide either a 'ticket_id' (e.g. PROJ-123) "
                "or a 'description' of the feature to test."
            )

        return {
            "ticket_id": ticket_id,
            "manual_description": manual_description,
        }

    # ── 2. PLAN ────────────────────────────────────────────────────────────────
    async def plan(self, understood: dict[str, Any]) -> dict[str, Any]:
        # Decide tool path: Jira API or manual description
        return {
            "use_jira": bool(understood.get("ticket_id")),
            **understood,
        }

    # ── 3. TOOL CALL ───────────────────────────────────────────────────────────
    async def call_tools(self, plan: dict[str, Any]) -> dict[str, Any]:
        if plan["use_jira"]:
            ticket = await fetch_jira_ticket(plan["ticket_id"])
            return {
                "ticket_id": ticket.id,
                "summary": ticket.summary,
                "description": ticket.description,
                "acceptance_criteria": ticket.acceptance_criteria,
                "issue_type": ticket.issue_type,
                "labels": ticket.labels,
            }
        else:
            return {
                "ticket_id": "MANUAL-001",
                "summary": "Manual description",
                "description": plan["manual_description"],
                "acceptance_criteria": "",
                "issue_type": "Story",
                "labels": [],
            }

    # ── 4. VALIDATE ────────────────────────────────────────────────────────────
    async def validate(self, tool_outputs: dict[str, Any]) -> None:
        desc = tool_outputs.get("description", "")
        if not desc or len(desc.strip()) < 20:
            raise ValueError(
                "The ticket description is too short to generate meaningful test cases. "
                "Please add more context."
            )

    # ── 5. RESPOND ─────────────────────────────────────────────────────────────
    async def respond(self, tool_outputs: dict[str, Any]) -> dict[str, Any]:
        ticket_id = tool_outputs["ticket_id"]
        summary = tool_outputs["summary"]
        description = tool_outputs["description"]
        ac = tool_outputs.get("acceptance_criteria", "")
        labels = ", ".join(tool_outputs.get("labels", [])) or "none"

        user_content = f"""Ticket: {ticket_id}
Summary: {summary}
Issue Type: {tool_outputs.get("issue_type", "Story")}
Labels: {labels}

Description:
{description}

{f"Acceptance Criteria:{chr(10)}{ac}" if ac else ""}

Generate a comprehensive test suite. Return ONLY the JSON object — nothing else."""

        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]

        raw_json = await self.llm.complete(
            messages,
            temperature=0.1,
            max_tokens=8192,
            response_format="json_object",
        )

        # Parse and validate against schema
        try:
            parsed = json.loads(raw_json)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"The AI model returned an incomplete or invalid JSON response: {e}. "
                "This can happen due to API limits or safety filters. Please try again."
            )

        # Inject runtime metadata
        parsed["generated_at"] = datetime.now(timezone.utc).isoformat()
        parsed["model_used"] = self.llm.model_name
        parsed["total_cases"] = len(parsed.get("cases", []))

        # Validate via Pydantic — raises ValidationError if schema is violated
        suite = TestSuite.model_validate(parsed)
        return suite.model_dump()
