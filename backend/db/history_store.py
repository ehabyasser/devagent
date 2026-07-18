"""
backend/db/history_store.py

CRUD layer for review_history table.

All functions are async and use the get_db() context manager.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from backend.db.database import get_db
from backend.schemas.history import HistorySummary, HistoryEntry, HistoryStats


# ── Write ──────────────────────────────────────────────────────────────────────

async def save_review(result: dict, diff_preview: str = "", language: str = "swift") -> str:
    """
    Persist a completed ReviewResult dict to the database.
    Returns the generated UUID.
    """
    review_id  = str(uuid.uuid4())
    scores     = result.get("scores", {})
    violations = result.get("violations", [])

    # Determine most-violated category for easy aggregate queries
    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO review_history (
                id, pr_title, language, reviewed_at, model_used, active_rules,
                score_overall, score_security, score_architecture, score_performance,
                score_maintainability, score_readability, score_testing, score_production,
                violation_count, approved, approved_reason,
                violations_json, summary, diff_preview
            ) VALUES (
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?
            )
            """,
            (
                review_id,
                result.get("pr_title", "Untitled PR"),
                language,
                result.get("reviewed_at") or datetime.now(timezone.utc).isoformat(),
                result.get("model_used", "unknown"),
                result.get("active_rules_count", 0),
                # Scores
                scores.get("overall", 0),
                scores.get("security", 0),
                scores.get("architecture", 0),
                scores.get("performance", 0),
                scores.get("maintainability", 0),
                scores.get("readability", 0),
                scores.get("testing", 0),
                scores.get("production_readiness", 0),
                # Summary fields
                len(violations),
                1 if result.get("approved") else 0,
                result.get("approved_reason", ""),
                json.dumps(violations),
                result.get("summary", ""),
                diff_preview[:500],  # truncate for preview
            ),
        )
        await db.commit()

    return review_id


# ── Read ───────────────────────────────────────────────────────────────────────

async def list_reviews(limit: int = 50, offset: int = 0) -> list[HistorySummary]:
    """Return lightweight summaries ordered by most recent first."""
    async with get_db() as db:
        cursor = await db.execute(
            """
            SELECT id, pr_title, language, reviewed_at, model_used, active_rules,
                   score_overall, violation_count, approved, diff_preview
            FROM review_history
            ORDER BY reviewed_at DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )
        rows = await cursor.fetchall()

    return [
        HistorySummary(
            id=row["id"],
            pr_title=row["pr_title"],
            language=row["language"],
            reviewed_at=row["reviewed_at"],
            model_used=row["model_used"],
            active_rules=row["active_rules"],
            score_overall=row["score_overall"],
            violation_count=row["violation_count"],
            approved=bool(row["approved"]),
            diff_preview=row["diff_preview"],
        )
        for row in rows
    ]


async def get_review(review_id: str) -> Optional[HistoryEntry]:
    """Return a full review entry including all scores and violations."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM review_history WHERE id = ?",
            (review_id,),
        )
        row = await cursor.fetchone()

    if not row:
        return None

    try:
        violations = json.loads(row["violations_json"] or "[]")
    except json.JSONDecodeError:
        violations = []

    return HistoryEntry(
        id=row["id"],
        pr_title=row["pr_title"],
        language=row["language"],
        reviewed_at=row["reviewed_at"],
        model_used=row["model_used"],
        active_rules=row["active_rules"],
        score_overall=row["score_overall"],
        score_security=row["score_security"],
        score_architecture=row["score_architecture"],
        score_performance=row["score_performance"],
        score_maintainability=row["score_maintainability"],
        score_readability=row["score_readability"],
        score_testing=row["score_testing"],
        score_production=row["score_production"],
        violation_count=row["violation_count"],
        approved=bool(row["approved"]),
        approved_reason=row["approved_reason"],
        violations=violations,
        summary=row["summary"],
        diff_preview=row["diff_preview"],
    )


# ── Delete ─────────────────────────────────────────────────────────────────────

async def delete_review(review_id: str) -> bool:
    """Delete a review by ID. Returns True if deleted, False if not found."""
    async with get_db() as db:
        cursor = await db.execute(
            "DELETE FROM review_history WHERE id = ?", (review_id,)
        )
        await db.commit()
        return cursor.rowcount > 0


# ── Stats ──────────────────────────────────────────────────────────────────────

async def get_stats() -> HistoryStats:
    """Compute aggregate statistics across all saved reviews."""
    async with get_db() as db:
        # Basic aggregates
        cursor = await db.execute(
            """
            SELECT
                COUNT(*)                        AS total,
                AVG(score_overall)              AS avg_overall,
                AVG(score_security)             AS avg_security,
                SUM(approved)                   AS approved_count,
                SUM(violation_count)            AS total_violations
            FROM review_history
            """
        )
        agg = await cursor.fetchone()

        # Reviews in last 7 days
        cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        cursor = await db.execute(
            "SELECT COUNT(*) AS cnt FROM review_history WHERE reviewed_at >= ?",
            (cutoff,),
        )
        recent = await cursor.fetchone()

        # Most violated category — parse violations JSON and tally categories
        cursor = await db.execute(
            "SELECT violations_json FROM review_history WHERE violations_json != '[]'"
        )
        all_rows = await cursor.fetchall()

    category_counts: dict[str, int] = {}
    for row in all_rows:
        try:
            viols = json.loads(row["violations_json"] or "[]")
        except json.JSONDecodeError:
            continue
        for v in viols:
            cat = v.get("category", "")
            if cat:
                category_counts[cat] = category_counts.get(cat, 0) + 1

    most_violated = max(category_counts, key=category_counts.get) if category_counts else None

    total = agg["total"] or 0
    return HistoryStats(
        total_reviews=total,
        avg_score_overall=round(agg["avg_overall"] or 0, 1),
        avg_score_security=round(agg["avg_security"] or 0, 1),
        approved_count=agg["approved_count"] or 0,
        total_violations=agg["total_violations"] or 0,
        most_violated_category=most_violated,
        reviews_last_7_days=recent["cnt"] or 0,
    )
