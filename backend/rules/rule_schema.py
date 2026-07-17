"""
backend/rules/rule_schema.py

Pydantic models for the rule system.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Severity(str, Enum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"
    info = "info"


class Category(str, Enum):
    architecture = "architecture"
    swift_best_practices = "swift_best_practices"
    concurrency = "concurrency"
    performance = "performance"
    memory_management = "memory_management"
    security = "security"
    networking = "networking"
    ui_ux = "ui_ux"
    testing = "testing"
    code_quality = "code_quality"
    git_hygiene = "git_hygiene"
    banking = "banking"
    custom = "custom"


class RuleExample(BaseModel):
    bad: str = ""
    good: str = ""


class Rule(BaseModel):
    id: str
    name: str
    category: str
    description: str
    severity: Severity = Severity.medium
    weight: int = Field(default=5, ge=1, le=10)
    enabled: bool = True
    auto_fix: bool = False
    auto_fix_hint: str = ""
    tags: list[str] = []
    examples: RuleExample = Field(default_factory=RuleExample)
    custom: bool = False
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class RuleUpdate(BaseModel):
    """Partial update — all fields optional."""
    name: Optional[str] = None
    description: Optional[str] = None
    severity: Optional[Severity] = None
    weight: Optional[int] = Field(default=None, ge=1, le=10)
    enabled: Optional[bool] = None
    auto_fix: Optional[bool] = None
    auto_fix_hint: Optional[str] = None
    tags: Optional[list[str]] = None
    examples: Optional[RuleExample] = None


class RuleCreate(BaseModel):
    """Fields required to create a new custom rule."""
    name: str
    category: str = "custom"
    description: str
    severity: Severity = Severity.medium
    weight: int = Field(default=5, ge=1, le=10)
    enabled: bool = True
    auto_fix: bool = False
    auto_fix_hint: str = ""
    tags: list[str] = []
    examples: RuleExample = Field(default_factory=RuleExample)
