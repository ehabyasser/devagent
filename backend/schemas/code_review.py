"""backend/schemas/code_review.py — Request/response schemas for code review."""
from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional


class ReviewRequest(BaseModel):
    pr_title: str = "Untitled PR"
    diff: str
    language: str = "swift"
    context: Optional[str] = None  # Optional: extra context about the codebase


class ViolationDetail(BaseModel):
    rule_id: str
    rule_name: str
    category: str
    severity: str
    explanation: str
    business_impact: str
    suggested_fix: str
    code_snippet: str
    auto_fix_available: bool = False
    line_hint: Optional[str] = None


class ScoreBreakdown(BaseModel):
    security: int = Field(ge=0, le=100)
    architecture: int = Field(ge=0, le=100)
    performance: int = Field(ge=0, le=100)
    maintainability: int = Field(ge=0, le=100)
    readability: int = Field(ge=0, le=100)
    testing: int = Field(ge=0, le=100)
    production_readiness: int = Field(ge=0, le=100)
    overall: int = Field(ge=0, le=100)


class ReviewResult(BaseModel):
    pr_title: str
    reviewed_at: str
    model_used: str
    active_rules_count: int
    scores: ScoreBreakdown
    violations: list[ViolationDetail]
    summary: str
    approved: bool
    approved_reason: str = ""
