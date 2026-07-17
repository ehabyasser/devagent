"""
backend/agents/code_review_agent.py

AI code reviewer. Uses the active rules from the rule store to build a
context-aware system prompt, then calls the LLM for structured JSON output.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from backend.agents.base_agent import BaseAgent
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
    "overall": 0-100  // weighted average
  }},
  "violations": [
    {{
      "rule_id": string,
      "rule_name": string,
      "category": string,
      "severity": "critical"|"high"|"medium"|"low"|"info",
      "explanation": string (why it's a problem, specific to the diff),
      "business_impact": string (banking/production consequence),
      "suggested_fix": string (concrete code suggestion),
      "code_snippet": string (the offending code from the diff),
      "auto_fix_available": boolean,
      "line_hint": string|null (e.g. "line 28")
    }}
  ],
  "summary": string (2-3 sentences, actionable, no fluff),
  "approved": boolean,
  "approved_reason": string
}}

Scoring guidance:
- Start each dimension at 100, deduct per severity: critical=-25, high=-15, medium=-8, low=-3, info=-1
- Cap deductions per dimension at -60
- Overall = weighted mean (security×2 + architecture + performance + maintainability + readability + testing + production_readiness) / 8

If no violations are found, return an empty violations array and high scores.
Be specific — quote the actual code from the diff, don't be generic.
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

    async def run(self, request: ReviewRequest) -> dict:
        # Load only enabled rules
        active_rules = get_all_rules(enabled=True)

        rules_block = _build_rules_block(active_rules)
        system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(
            count=len(active_rules),
            rules_block=rules_block,
        )

        user_content = f"PR Title: {request.pr_title}\nLanguage: {request.language}\n"
        if request.context:
            user_content += f"Context: {request.context}\n"
        user_content += f"\n## Git Diff\n{request.diff}"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
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
            raise ValueError(
                f"AI returned invalid JSON: {e}. Please try again."
            )

        # Inject runtime metadata
        parsed["reviewed_at"] = datetime.now(timezone.utc).isoformat()
        parsed["model_used"] = self.llm.model_name
        parsed["active_rules_count"] = len(active_rules)
        parsed.setdefault("pr_title", request.pr_title)
        parsed.setdefault("approved", False)
        parsed.setdefault("approved_reason", "")

        # Validate via Pydantic
        result = ReviewResult.model_validate(parsed)
        return result.model_dump()
