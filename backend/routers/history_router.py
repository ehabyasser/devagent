"""
backend/routers/history_router.py

REST API for review history.

Endpoints:
    GET    /api/history          → list recent reviews (summary)
    GET    /api/history/stats    → aggregate statistics
    GET    /api/history/{id}     → full review detail
    DELETE /api/history/{id}     → delete one entry
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from backend.db.history_store import (
    list_reviews,
    get_review,
    delete_review,
    get_stats,
)
from backend.schemas.history import HistorySummary, HistoryEntry, HistoryStats

router = APIRouter(prefix="/api/history", tags=["history"])


@router.get("", response_model=list[HistorySummary])
async def history_list(
    limit: int  = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """Return recent code review summaries, newest first."""
    return await list_reviews(limit=limit, offset=offset)


@router.get("/stats", response_model=HistoryStats)
async def history_stats():
    """Return aggregate statistics across all saved reviews."""
    return await get_stats()


@router.get("/{review_id}", response_model=HistoryEntry)
async def history_detail(review_id: str):
    """Return full details of a single review including all scores and violations."""
    entry = await get_review(review_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Review not found.")
    return entry


@router.delete("/{review_id}", status_code=204)
async def history_delete(review_id: str):
    """Permanently delete a review from history."""
    deleted = await delete_review(review_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Review not found.")
