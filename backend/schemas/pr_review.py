"""
schemas/pr_review.py

JSON contract for the PR Review agent output.
Severity mirrors the GitHub / Linear convention so teams can map to their tracker.
"""
from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, Field
from typing import Annotated, Optional


class Severity(str, Enum):
    CRITICAL = "critical"    # Must fix before merge — security / crash risk
    HIGH = "high"            # Significant arch / perf problem
    MEDIUM = "medium"        # Best-practice violation
    LOW = "low"              # Style / naming suggestion
    INFO = "info"            # Observation, no action required


class ReviewCategory(str, Enum):
    ARCHITECTURE = "architecture"
    SWIFT_BEST_PRACTICES = "swift_best_practices"
    PERFORMANCE = "performance"
    SECURITY = "security"
    NAMING = "naming"
    GENERAL = "general"


class CodeLocation(BaseModel):
    file_path: str
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    snippet: Optional[str] = Field(
        default=None,
        description="Relevant code excerpt (≤ 10 lines)"
    )


class ReviewIssue(BaseModel):
    id: str                         # e.g. "PR-007"
    category: ReviewCategory
    severity: Severity
    title: str
    description: str
    location: Optional[CodeLocation] = None
    suggestion: Annotated[
        str,
        Field(description="Concrete, actionable fix or improvement")
    ]
    references: list[str] = Field(
        default_factory=list,
        description="Apple docs / SE proposals / OWASP links"
    )


class SecretDetection(BaseModel):
    found: bool
    occurrences: list[dict] = Field(default_factory=list)


class PRReview(BaseModel):
    """Top-level output returned by the PR Review agent."""
    pr_title: str
    diff_hash: str                  # SHA-256 of the raw diff for deduplication
    reviewed_at: str                # ISO-8601 timestamp
    model_used: str
    files_changed: int
    lines_added: int
    lines_removed: int
    secret_scan: SecretDetection
    total_issues: int
    issues: list[ReviewIssue]
    summary: Annotated[
        str,
        Field(description="Executive 3-sentence summary of the PR quality")
    ]
    merge_recommendation: Annotated[
        str,
        Field(description="approve | request_changes | comment")
    ]
