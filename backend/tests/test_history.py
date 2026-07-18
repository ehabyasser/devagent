"""
backend/tests/test_history.py

Integration tests for the review history CRUD layer.
Uses a temporary SQLite database so tests are isolated.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest
import pytest_asyncio

# ── Point history store at a temp DB before importing anything ──────────────────
_TMP_DB = tempfile.mktemp(suffix=".db")
os.environ["DATABASE_PATH"] = _TMP_DB

import backend.db.database as _db_mod
_db_mod.DB_PATH = Path(_TMP_DB)

from backend.db.database import init_db
from backend.db.history_store import (
    save_review,
    list_reviews,
    get_review,
    delete_review,
    get_stats,
)


# ── Fixtures ────────────────────────────────────────────────────────────────────

SAMPLE_RESULT = {
    "pr_title": "feat: Add Stripe integration",
    "reviewed_at": "2026-07-18T10:00:00+00:00",
    "model_used": "gemini-flash",
    "active_rules_count": 5,
    "scores": {
        "overall": 72,
        "security": 60,
        "architecture": 80,
        "performance": 75,
        "maintainability": 70,
        "readability": 85,
        "testing": 65,
        "production_readiness": 55,
    },
    "violations": [
        {
            "rule_id": "SEC-001",
            "rule_name": "No hardcoded secrets",
            "category": "security",
            "severity": "critical",
            "explanation": "API key hardcoded",
            "business_impact": "Secret exposure",
            "suggested_fix": "Use env var",
            "code_snippet": 'let key = "sk_live_xxx"',
            "auto_fix_available": True,
            "line_hint": "line 12",
        }
    ],
    "summary": "One critical security violation found.",
    "approved": False,
    "approved_reason": "",
}


@pytest.fixture(autouse=True, scope="module")
def event_loop_policy():
    """Use default event loop policy for pytest-asyncio."""
    import asyncio
    asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())


@pytest.fixture(autouse=True, scope="module")
def setup_db():
    """Create fresh DB schema before tests run (sync wrapper)."""
    import asyncio
    loop = asyncio.new_event_loop()
    loop.run_until_complete(init_db())
    yield
    loop.close()
    try:
        Path(_TMP_DB).unlink(missing_ok=True)
    except Exception:
        pass


# ── Tests ───────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_save_review_returns_uuid():
    """save_review() should return a non-empty string UUID."""
    review_id = await save_review(SAMPLE_RESULT, diff_preview="diff --git a/...", language="swift")
    assert isinstance(review_id, str)
    assert len(review_id) == 36  # UUID4 format


@pytest.mark.asyncio
async def test_list_reviews_returns_entries():
    """list_reviews() should return at least the saved review."""
    entries = await list_reviews(limit=10)
    assert len(entries) >= 1
    first = entries[0]
    assert first.pr_title == "feat: Add Stripe integration"
    assert first.score_overall == 72
    assert first.violation_count == 1
    assert first.approved is False


@pytest.mark.asyncio
async def test_get_review_full_detail():
    """get_review() should return all scores and violations."""
    # Save a fresh one so we have a known ID
    review_id = await save_review(SAMPLE_RESULT, diff_preview="preview...", language="swift")
    entry = await get_review(review_id)

    assert entry is not None
    assert entry.id == review_id
    assert entry.score_security == 60
    assert entry.score_architecture == 80
    assert entry.score_production == 55
    assert len(entry.violations) == 1
    assert entry.violations[0]["rule_id"] == "SEC-001"
    assert entry.summary == "One critical security violation found."


@pytest.mark.asyncio
async def test_get_review_not_found():
    """get_review() should return None for unknown IDs."""
    result = await get_review("00000000-0000-0000-0000-000000000000")
    assert result is None


@pytest.mark.asyncio
async def test_delete_review():
    """delete_review() should remove the entry and return True."""
    review_id = await save_review(SAMPLE_RESULT, language="kotlin")
    deleted = await delete_review(review_id)
    assert deleted is True

    # Confirm it's gone
    entry = await get_review(review_id)
    assert entry is None


@pytest.mark.asyncio
async def test_delete_nonexistent_returns_false():
    """delete_review() on a missing ID should return False."""
    result = await delete_review("nonexistent-id")
    assert result is False


@pytest.mark.asyncio
async def test_list_reviews_pagination():
    """Pagination via limit/offset should work correctly."""
    # Save 3 more reviews
    for i in range(3):
        result = {**SAMPLE_RESULT, "pr_title": f"PR-{i}"}
        await save_review(result)

    all_entries   = await list_reviews(limit=100)
    page1         = await list_reviews(limit=2, offset=0)
    page2         = await list_reviews(limit=2, offset=2)

    assert len(page1) == 2
    # page2 has at least some entries (may overlap with page1 items from DB)
    assert len(page2) >= 1
    # No duplicate IDs between pages when they're non-overlapping slices
    page1_ids = {e.id for e in page1}
    page2_ids = {e.id for e in page2}
    assert page1_ids.isdisjoint(page2_ids)


@pytest.mark.asyncio
async def test_stats_aggregate():
    """get_stats() should return correct aggregate data."""
    stats = await get_stats()

    assert stats.total_reviews >= 1
    assert 0 <= stats.avg_score_overall <= 100
    assert stats.total_violations >= 1
    assert stats.most_violated_category == "security"  # all our samples have security violations
