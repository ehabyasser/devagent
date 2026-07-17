"""backend/routers/review_router.py — Code review endpoint."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.agents.code_review_agent import CodeReviewAgent
from backend.llm import get_llm
from backend.schemas.code_review import ReviewRequest

router = APIRouter(prefix="/api/review", tags=["review"])


@router.post("")
async def run_code_review(request: ReviewRequest) -> dict:
    if not request.diff.strip():
        raise HTTPException(status_code=422, detail="Diff cannot be empty.")

    try:
        llm = get_llm()
        agent = CodeReviewAgent(llm)
        return await agent.review(request)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
