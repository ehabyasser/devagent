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
        "You are a senior software architect helping engineers write clear context "
        "for AI-powered code reviews.\n\n"
        "When the user explains what their code change does, generate professional "
        "additional context for the reviewer including:\n"
        "1. A 2-3 sentence summary of the change's purpose and scope\n"
        "2. Key technical decisions or trade-offs made\n"
        "3. Banking/security/compliance considerations if applicable\n"
        "4. What areas to focus the review on\n"
        "5. Testing approach\n\n"
        "Write in plain text. Professional and concise. No markdown headers. "
        "Keep it under 200 words."
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
    async for token in llm.stream(messages, temperature=0.5, max_tokens=512):
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
