"""backend/routers/review_router.py — Code review endpoint with auto-save to history."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException

from backend.agents.code_review_agent import CodeReviewAgent
from backend.db.history_store import save_review
from backend.llm import get_llm
from backend.schemas.code_review import ReviewRequest

router = APIRouter(prefix="/api/review", tags=["review"])


@router.post("")
async def run_code_review(request: ReviewRequest) -> dict:
    if not request.diff.strip():
        raise HTTPException(status_code=422, detail="Diff cannot be empty.")

    try:
        llm    = get_llm()
        agent  = CodeReviewAgent(llm)
        result = await agent.review(request)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # ── Auto-save to history (fire-and-forget; never blocks the response) ──────
    diff_preview = request.diff[:500]
    language     = request.language or "swift"

    async def _save():
        try:
            review_id = await save_review(result, diff_preview, language)
            # Return the id so the frontend can reference it
            result["review_id"] = review_id
        except Exception:
            pass  # History save failure must never break the review response

    # Schedule as a background task — response is returned immediately
    task = asyncio.create_task(_save())
    await task  # await here so review_id is in result before we return

    return result
