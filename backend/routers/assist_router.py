"""
routers/assist_router.py

Context-aware AI writing assistant.
Helps users write proper feature descriptions, code review context, and rule definitions.
Uses SSE streaming so the response appears token-by-token in the UI.
"""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.llm import get_llm

router = APIRouter(prefix="/api", tags=["assist"])

# ── System prompts per mode ────────────────────────────────────────────────────
_PROMPTS: dict[str, str] = {
    "testgen": (
        "You are an expert QA engineer and product manager helping teams write "
        "precise feature descriptions for AI-powered test case generation.\n\n"
        "When the user describes a feature informally, transform it into a well-structured "
        "feature description with:\n"
        "1. A clear user story: 'As a [user], I want [goal] so that [benefit]'\n"
        "2. 5-8 Acceptance Criteria covering: happy path, edge cases, error scenarios, "
        "   security considerations, and performance expectations\n"
        "3. Any banking/fintech compliance considerations if relevant\n\n"
        "Write in plain text with numbered acceptance criteria. "
        "Be specific and testable. No markdown headers. Keep it under 300 words."
    ),
    "codereview": (
        "You are a senior software architect and iOS engineer specializing in banking apps.\n\n"
        "You have TWO modes based on what the user asks:\n\n"
        "MODE A — CONTEXT GENERATION:\n"
        "If the user describes a code change (what it does, what was changed, etc.), "
        "generate professional additional context for the reviewer including:\n"
        "1. A 2-3 sentence summary of the change's purpose and scope\n"
        "2. Key technical decisions or trade-offs made\n"
        "3. Banking/security/compliance considerations if applicable\n"
        "4. What areas to focus the review on\n"
        "5. Testing approach\n"
        "Write in plain text. Professional and concise. Keep it under 200 words.\n\n"
        "MODE B — GIT DIFF EXAMPLE:\n"
        "If the user asks for a 'git diff example', 'sample diff', 'test diff', 'example diff', "
        "or anything similar, generate a REALISTIC git diff in proper unified diff format for a "
        "banking iOS Swift application. The diff should:\n"
        "- Be 40-80 lines of actual unified diff (with --- a/ +++ b/ @@ headers)\n"
        "- Include realistic Swift banking code (authentication, payment, API calls, etc.)\n"
        "- Intentionally contain 2-3 code issues for the AI reviewer to find "
        "(e.g. missing error handling, hardcoded values, insecure storage, race conditions)\n"
        "- Have a realistic filename like Sources/Authentication/LoginViewModel.swift\n"
        "Output ONLY the raw git diff text, no explanation before or after."
    ),
    "rules": (
        "You are an expert software architect and security engineer helping teams "
        "define custom code review rules for a banking iOS application.\n\n"
        "When the user describes a coding standard or practice they want to enforce, "
        "generate a clear rule description including:\n"
        "1. What the rule specifically enforces (one clear sentence)\n"
        "2. Why it matters — especially security, compliance (PCI-DSS, GDPR, banking regs), "
        "   or reliability reasons\n"
        "3. What a violation looks like in code\n"
        "4. The business impact of not following this rule\n\n"
        "Write in plain text. Authoritative and precise. No markdown headers. "
        "Keep it under 200 words."
    ),
}

_LABELS = {
    "testgen": "Test Generator description",
    "codereview": "Code Review context",
    "rules": "Rule description",
}


class AssistRequest(BaseModel):
    message: str = Field(..., min_length=3, max_length=2000)
    mode: str = Field(default="testgen", pattern=r"^(testgen|codereview|rules)$")
    history: list[dict] = Field(default_factory=list)


async def _stream_assist(req: AssistRequest):
    """SSE generator — yields data: <chunk>\n\n for each token."""
    llm = get_llm()
    system = _PROMPTS.get(req.mode, _PROMPTS["testgen"])

    messages = [{"role": "system", "content": system}]

    # Include conversation history (last 6 turns max to keep context tight)
    for turn in req.history[-6:]:
        if turn.get("role") in ("user", "assistant") and turn.get("content"):
            messages.append({"role": turn["role"], "content": turn["content"]})

    messages.append({"role": "user", "content": req.message})

    import json
    async for token in llm.stream(messages, temperature=0.5, max_tokens=2048):
        yield f"data: {json.dumps({'token': token})}\n\n"

    yield "data: [DONE]\n\n"


@router.post("/assist/stream")
async def assist_stream(req: AssistRequest):
    return StreamingResponse(
        _stream_assist(req),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ── Rules Suggestion endpoint ──────────────────────────────────────────────
_RULES_SUGGEST_SYSTEM = """You are an expert software architect and security engineer for a banking iOS application.
Given the user's description of a coding standard or practice, generate 3–5 concrete, actionable code review rules.

Return ONLY a valid JSON array (no markdown, no explanation) with this exact structure:
[
  {
    "name": "Short rule name (max 60 chars)",
    "category": "one of: architecture|swift_best_practices|concurrency|performance|memory_management|security|networking|ui_ux|testing|code_quality|git_hygiene|banking|custom",
    "description": "Clear, specific description of what to enforce and why (2-4 sentences)",
    "severity": "one of: critical|high|medium|low|info",
    "weight": <integer 1-10>,
    "auto_fix": false,
    "tags": ["tag1", "tag2"],
    "examples": {
      "bad": "Brief bad code example",
      "good": "Brief good code example"
    }
  }
]

Make rules specific to banking/fintech iOS (Swift) development. Severity must reflect actual risk."""


class RulesSuggestRequest(BaseModel):
    description: str = Field(..., min_length=5, max_length=2000)


class SuggestedRule(BaseModel):
    name: str
    category: str
    description: str
    severity: str = "medium"
    weight: int = 5
    auto_fix: bool = False
    tags: list[str] = []
    examples: dict = {}


@router.post("/assist/rules-suggest", response_model=list[SuggestedRule])
async def rules_suggest(req: RulesSuggestRequest):
    import json
    llm = get_llm()
    messages = [
        {"role": "system", "content": _RULES_SUGGEST_SYSTEM},
        {"role": "user",   "content": f"Generate rules for: {req.description}"},
    ]
    raw = await llm.complete(messages, temperature=0.3, max_tokens=2048, response_format="json_object")
    # llm may return a JSON object wrapping the array
    try:
        parsed = json.loads(raw)
    except Exception:
        # strip markdown fences if present
        import re
        cleaned = re.sub(r"```(?:json)?|```", "", raw).strip()
        parsed = json.loads(cleaned)

    if isinstance(parsed, dict):
        # some models wrap in {"rules": [...]}
        for v in parsed.values():
            if isinstance(v, list):
                parsed = v
                break

    return [SuggestedRule(**r) for r in parsed[:5]]
