"""
backend/agents/code_review_agent.py

AI code reviewer. Implements the BaseAgent 5-stage loop.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from backend.agents.base_agent import BaseAgent, AgentContext
from backend.llm.base_llm import BaseLLM
from backend.rules.rule_store import get_all_rules
from backend.schemas.code_review import ReviewResult, ReviewRequest

_SYSTEM_PROMPT_TEMPLATE = """You are a senior bank-grade code reviewer and software architect.
You review code changes (git diffs) against an active ruleset and produce structured JSON output.

Your job:
1. Analyze the diff carefully.
2. Identify EVERY violation of the active rules listed below.
3. Score the PR on 7 dimensions (0-100 each).
4. Return ONLY valid JSON — no markdown, no commentary outside the JSON.

## Active Rules ({count} rules)
{rules_block}

## Output Schema (return EXACTLY this JSON structure):
{{
  "pr_title": string,
  "reviewed_at": string (ISO-8601),
  "model_used": string,
  "active_rules_count": number,
  "scores": {{
    "security": 0-100,
    "architecture": 0-100,
    "performance": 0-100,
    "maintainability": 0-100,
    "readability": 0-100,
    "testing": 0-100,
    "production_readiness": 0-100,
    "overall": 0-100
  }},
  "violations": [
    {{
      "rule_id": string,
      "rule_name": string,
      "category": string,
      "severity": "critical"|"high"|"medium"|"low"|"info",
      "explanation": string,
      "business_impact": string,
      "suggested_fix": string,
      "code_snippet": string,
      "auto_fix_available": boolean,
      "line_hint": string|null
    }}
  ],
  "summary": string,
  "approved": boolean,
  "approved_reason": string
}}

Scoring: start at 100, deduct per severity — critical=-25, high=-15, medium=-8, low=-3, info=-1.
Overall = weighted mean (security×2 + architecture + performance + maintainability + readability + testing + production_readiness) / 8.
If no violations, return empty array and high scores.
Be specific — quote actual code from the diff.
"""


def _build_rules_block(rules) -> str:
    lines = []
    for r in rules:
        lines.append(
            f"[{r.id}] {r.name} | Category: {r.category} | Severity: {r.severity} | Weight: {r.weight}/10\n"
            f"  → {r.description}"
        )
    return "\n\n".join(lines)


class CodeReviewAgent(BaseAgent):
    def __init__(self, llm: BaseLLM) -> None:
        super().__init__(llm)

    # ── Stage 1: UNDERSTAND ─────────────────────────────────────────────────
    async def understand(self, ctx: AgentContext) -> dict:
        req = ctx.raw_input
        if not req.get("diff", "").strip():
            raise ValueError("Diff cannot be empty.")
        return {
            "pr_title": req.get("pr_title", "Untitled PR"),
            "diff": req["diff"],
            "language": req.get("language", "swift"),
            "context": req.get("context") or "",
        }

    # ── Stage 2: PLAN ───────────────────────────────────────────────────────
    async def plan(self, understood: dict) -> dict:
        active_rules = get_all_rules(enabled=True)
        if not active_rules:
            raise ValueError(
                "No active rules found. Enable at least one rule in the Rules Manager before running a code review."
            )
        rules_block = _build_rules_block(active_rules)
        system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(
            count=len(active_rules),
            rules_block=rules_block,
        )
        return {**understood, "system_prompt": system_prompt, "active_rules_count": len(active_rules)}

    # ── Stage 3: CALL TOOLS (no external tools for this agent) ─────────────
    async def call_tools(self, plan: dict) -> dict:
        # No external tools needed — return plan as-is
        return plan

    # ── Stage 4: VALIDATE ───────────────────────────────────────────────────
    async def validate(self, tool_outputs: dict) -> None:
        if not tool_outputs.get("diff"):
            raise ValueError("Diff is missing after tool stage.")
        if not tool_outputs.get("system_prompt"):
            raise ValueError("System prompt was not built.")

    # ── Stage 5: RESPOND ────────────────────────────────────────────────────
    async def respond(self, tool_outputs: dict) -> dict:
        messages = [
            {"role": "system", "content": tool_outputs["system_prompt"]},
            {"role": "user", "content": self._build_user_message(tool_outputs)},
        ]

        raw_json = await self.llm.complete(
            messages,
            temperature=0.1,
            max_tokens=8192,
            response_format="json_object",
        )

        try:
            parsed = json.loads(raw_json)
        except json.JSONDecodeError as e:
            raise ValueError(f"AI returned invalid JSON: {e}")

        parsed["reviewed_at"] = datetime.now(timezone.utc).isoformat()
        parsed["model_used"] = self.llm.model_name
        parsed["active_rules_count"] = tool_outputs["active_rules_count"]
        parsed.setdefault("pr_title", tool_outputs["pr_title"])
        parsed.setdefault("approved", False)
        parsed.setdefault("approved_reason", "")

        result = ReviewResult.model_validate(parsed)
        return result.model_dump()

    def _build_user_message(self, inputs: dict) -> str:
        msg = f"PR Title: {inputs['pr_title']}\nLanguage: {inputs['language']}\n"
        if inputs.get("context"):
            msg += f"Context: {inputs['context']}\n"
        msg += f"\n## Git Diff\n{inputs['diff']}"
        return msg

    # ── Convenience: run a ReviewRequest directly ────────────────────────────
    async def review(self, request: ReviewRequest) -> dict:
        from backend.agents.base_agent import AgentContext
        ctx = AgentContext(raw_input={
            "pr_title": request.pr_title,
            "diff": request.diff,
            "language": request.language,
            "context": request.context,
        })
        result = await self.run(ctx.raw_input)
        if "error" in result:
            raise ValueError(result["error"])
        return result["result"]
