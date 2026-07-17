"""
schemas/test_case.py

JSON contract for the Test Case Generator output.
Every field is typed; the frontend and any downstream consumer can rely on this shape.
"""
from __future__ import annotations

from enum import Enum
from typing import Annotated
from pydantic import BaseModel, Field


class TestCategory(str, Enum):
    HAPPY_PATH = "happy_path"
    NEGATIVE = "negative"
    BOUNDARY = "boundary"
    REGRESSION = "regression"


class Priority(str, Enum):
    P0 = "P0"   # Critical / Blocker
    P1 = "P1"   # High
    P2 = "P2"   # Medium
    P3 = "P3"   # Low


class TestStep(BaseModel):
    step_number: int
    action: Annotated[str, Field(description="What the tester does")]
    expected_result: Annotated[str, Field(description="Observable outcome after the action")]


class TestCase(BaseModel):
    id: Annotated[str, Field(description="e.g. TC-001")]
    title: str
    category: TestCategory
    priority: Priority
    preconditions: list[str] = Field(default_factory=list)
    steps: list[TestStep]
    expected_outcome: str
    tags: list[str] = Field(default_factory=list)


class TestSuite(BaseModel):
    """Top-level output returned by the Test Case Generator agent."""
    ticket_id: str
    ticket_summary: str
    generated_at: str          # ISO-8601 timestamp
    model_used: str
    total_cases: int
    cases: list[TestCase]
    coverage_notes: Annotated[
        str,
        Field(description="Brief note on what is NOT covered and why")
    ] = ""
