"""
backend/schemas/history.py

Pydantic models for Review History API responses.
"""
from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel


class HistorySummary(BaseModel):
    """Lightweight entry shown in the history list."""
    id: str
    pr_title: str
    language: str
    reviewed_at: str
    model_used: str
    active_rules: int
    score_overall: int
    violation_count: int
    approved: bool
    diff_preview: str


class HistoryEntry(HistorySummary):
    """Full entry with scores breakdown, violations, and summary."""
    score_security: int
    score_architecture: int
    score_performance: int
    score_maintainability: int
    score_readability: int
    score_testing: int
    score_production: int
    violations: list[dict[str, Any]]
    summary: str
    approved_reason: str


class HistoryStats(BaseModel):
    """Aggregate statistics across all saved reviews."""
    total_reviews: int
    avg_score_overall: float
    avg_score_security: float
    approved_count: int
    total_violations: int
    most_violated_category: Optional[str]  # e.g. "security"
    reviews_last_7_days: int
