"""
routers/agent_router.py

POST /api/agent/test-gen    → runs TestGenAgent
POST /api/agent/pr-review   → runs PRReviewAgent

Both endpoints accept JSON, run the full agent loop, and return structured JSON.
SSE streaming is available at /api/agent/pr-review/stream for real-time UI updates.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.agents.test_gen_agent import TestGenAgent
from backend.agents.pr_review_agent import PRReviewAgent
from backend.llm import get_llm

router = APIRouter(prefix="/api/agent", tags=["agent"])


# ── Request models ─────────────────────────────────────────────────────────────

class TestGenRequest(BaseModel):
    ticket_id: Optional[str] = Field(
        default=None,
        description="Jira ticket ID, e.g. PROJ-123",
        examples=["PROJ-123"],
    )
    description: Optional[str] = Field(
        default=None,
        description="Manual feature description (used when no ticket_id is provided)",
    )


class PRReviewRequest(BaseModel):
    pr_title: str = Field(
        default="Untitled PR",
        description="Title of the pull request",
    )
    diff: str = Field(
        description="Raw unified git diff output from 'git diff main...branch'",
    )


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/test-gen")
async def test_gen(request: TestGenRequest) -> dict[str, Any]:
    """
    Generate professional test cases from a Jira ticket or feature description.
    Returns a TestSuite JSON object.
    """
    try:
        agent = TestGenAgent(llm=get_llm())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    result = await agent.run(request.model_dump())

    if "error" in result:
        raise HTTPException(status_code=422, detail=result["error"])

    return result["result"]


@router.post("/pr-review")
async def pr_review(request: PRReviewRequest) -> dict[str, Any]:
    """
    Review a pull request from a git diff.
    Returns a PRReview JSON object with structured issues.
    """
    try:
        agent = PRReviewAgent(llm=get_llm())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    result = await agent.run(request.model_dump())

    if "error" in result:
        raise HTTPException(status_code=422, detail=result["error"])

    return result["result"]


@router.post("/pr-review/stream")
async def pr_review_stream(request: PRReviewRequest) -> StreamingResponse:
    """
    Server-Sent Events endpoint for real-time PR review streaming.
    Streams LLM tokens as they arrive, then sends a final 'done' event
    with the structured result.
    """
    async def event_generator():
        try:
            agent = PRReviewAgent(llm=get_llm())
        except ValueError as e:
            payload = json.dumps({"error": str(e)})
            yield f"event: error\ndata: {payload}\n\n"
            return
        result = await agent.run(request.model_dump())

        if "error" in result:
            payload = json.dumps({"error": result["error"]})
            yield f"event: error\ndata: {payload}\n\n"
            return

        # Stream the summary character by character for a typing effect
        summary = result["result"].get("summary", "")
        for char in summary:
            yield f"event: token\ndata: {json.dumps({'token': char})}\n\n"

        # Send the full result as the final event
        yield f"event: done\ndata: {json.dumps(result['result'])}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
