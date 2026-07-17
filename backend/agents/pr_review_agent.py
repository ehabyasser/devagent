"""
agents/pr_review_agent.py

PR Review Agent.

Understand → validate diff input
Plan      → parse diff, run secret scan, truncate for LLM
Tool Call → parse_diff + scan_diff_for_secrets
Validate  → ensure diff has meaningful content
Respond   → prompt LLM with context, parse PRReview schema
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from backend.agents.base_agent import BaseAgent, AgentContext
from backend.llm.base_llm import BaseLLM
from backend.schemas.pr_review import PRReview, SecretDetection
from backend.tools.diff_parser import parse_diff
from backend.tools.secret_scanner import scan_diff_for_secrets


_SYSTEM_PROMPT = """You are a principal iOS/Swift engineer conducting a thorough, rigorous code review.
You review pull requests with the critical eye of a CTO who cares deeply about long-term code quality.

Your review covers five dimensions:
1. ARCHITECTURE — SOLID principles, separation of concerns, dependency direction, module coupling
2. SWIFT_BEST_PRACTICES — Swift idioms, optionals, error handling, Sendable/concurrency, API design
3. PERFORMANCE — Memory leaks, retain cycles, unnecessary allocations, O(n²) loops, main-thread blocking  
4. SECURITY — Hardcoded credentials, insecure storage (UserDefaults for sensitive data), improper input validation, SQL injection, XXE
5. NAMING — Clarity, consistency with Swift API guidelines, abbreviations, misleading names

Rules:
1. Return ONLY valid JSON — no markdown, no commentary outside JSON.
2. Be specific: quote the exact problematic code in 'snippet'.
3. Provide a concrete 'suggestion' — not just "fix this".
4. Do NOT flag stylistic preferences as 'critical'.
5. 'merge_recommendation' must be: "approve" | "request_changes" | "comment"
6. Only use "approve" if there are zero critical or high issues.
7. Include issue ID in format PR-001, PR-002, etc.
8. Limit the issues array to a maximum of 2 or 3 of the most critical issues. Keep descriptions and suggestions extremely concise to avoid exceeding output token limits.

Return a JSON object matching this TypeScript interface:
{
  pr_title: string,
  diff_hash: string,
  reviewed_at: string,
  model_used: string,
  files_changed: number,
  lines_added: number,
  lines_removed: number,
  secret_scan: { found: boolean, occurrences: any[] },
  total_issues: number,
  issues: Array<{
    id: string,
    category: "architecture" | "swift_best_practices" | "performance" | "security" | "naming" | "general",
    severity: "critical" | "high" | "medium" | "low" | "info",
    title: string,
    description: string,
    location: { file_path: string, start_line?: number, end_line?: number, snippet?: string } | null,
    suggestion: string,
    references: string[]
  }>,
  summary: string,
  merge_recommendation: "approve" | "request_changes" | "comment"
}
"""


class PRReviewAgent(BaseAgent):
    def __init__(self, llm: BaseLLM) -> None:
        super().__init__(llm)

    # ── 1. UNDERSTAND ──────────────────────────────────────────────────────────
    async def understand(self, ctx: AgentContext) -> dict[str, Any]:
        data = ctx.raw_input
        diff_text: Optional[str] = data.get("diff")
        pr_title: str = data.get("pr_title", "Untitled PR")

        if not diff_text or not diff_text.strip():
            raise ValueError(
                "A 'diff' field containing a unified git diff is required. "
                "Run 'git diff main...your-branch' and paste the output."
            )

        if len(diff_text) > 500_000:
            raise ValueError(
                "Diff exceeds 500 KB. Please review in smaller chunks "
                "or filter to the most critical files."
            )

        return {"diff": diff_text, "pr_title": pr_title}

    # ── 2. PLAN ────────────────────────────────────────────────────────────────
    async def plan(self, understood: dict[str, Any]) -> dict[str, Any]:
        return understood  # Tools are always the same for PR review

    # ── 3. TOOL CALL ───────────────────────────────────────────────────────────
    async def call_tools(self, plan: dict[str, Any]) -> dict[str, Any]:
        diff = plan["diff"]

        # Run both tools; they are pure functions — no side effects
        diff_summary = parse_diff(diff)
        secret_occurrences = scan_diff_for_secrets(diff)

        return {
            "pr_title": plan["pr_title"],
            "diff_summary": diff_summary,
            "secret_occurrences": secret_occurrences,
        }

    # ── 4. VALIDATE ────────────────────────────────────────────────────────────
    async def validate(self, tool_outputs: dict[str, Any]) -> None:
        ds = tool_outputs["diff_summary"]
        if ds.files_changed == 0:
            raise ValueError("The diff contains no changed files.")
        if ds.lines_added + ds.lines_removed == 0:
            raise ValueError("The diff contains no line changes.")

    # ── 5. RESPOND ─────────────────────────────────────────────────────────────
    async def respond(self, tool_outputs: dict[str, Any]) -> dict[str, Any]:
        ds = tool_outputs["diff_summary"]
        secrets = tool_outputs["secret_occurrences"]
        pr_title = tool_outputs["pr_title"]

        secret_note = ""
        if secrets:
            lines = [
                f"  - {s.rule_name} in {s.file_path}:{s.line_number} (masked: {s.masked_value})"
                for s in secrets
            ]
            secret_note = (
                "\n⚠️  SECRET SCAN ALERT — The following potential secrets were detected "
                "in added lines. These MUST be flagged as CRITICAL security issues:\n"
                + "\n".join(lines)
            )

        file_context = "\n".join(
            f"  {f['path']}: +{f['added']} -{f['removed']} lines, {f['hunks']} hunks"
            for f in ds.file_summaries
        )

        user_content = f"""PR Title: {pr_title}
Files changed: {ds.files_changed}
Lines added: {ds.lines_added} | Lines removed: {ds.lines_removed}
Diff hash: {ds.diff_hash}

Files:
{file_context}
{secret_note}

Git Diff:
{ds.truncated_diff}

Produce a thorough code review. Return ONLY the JSON object."""

        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]

        raw_json = await self.llm.complete(
            messages,
            temperature=0.15,
            max_tokens=4096,
            response_format="json_object",
        )

        try:
            parsed = json.loads(raw_json)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"The AI model returned an incomplete or invalid JSON response: {e}. "
                "This can happen due to API limits or safety filters. Please try again."
            )

        # Inject tool-derived metadata (don't trust LLM for these)
        parsed["diff_hash"] = ds.diff_hash
        parsed["files_changed"] = ds.files_changed
        parsed["lines_added"] = ds.lines_added
        parsed["lines_removed"] = ds.lines_removed
        parsed["reviewed_at"] = datetime.now(timezone.utc).isoformat()
        parsed["model_used"] = self.llm.model_name
        parsed["total_issues"] = len(parsed.get("issues", []))

        # Build deterministic secret_scan from our scanner, not LLM
        parsed["secret_scan"] = {
            "found": len(secrets) > 0,
            "occurrences": [
                {
                    "rule": s.rule_name,
                    "file": s.file_path,
                    "line": s.line_number,
                    "masked_value": s.masked_value,
                }
                for s in secrets
            ],
        }

        # Validate against Pydantic schema
        review = PRReview.model_validate(parsed)
        return review.model_dump()
