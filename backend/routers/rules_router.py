"""backend/routers/rules_router.py — REST API for rule management."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from backend.rules.rule_schema import Rule, RuleCreate, RuleUpdate
from backend.rules.rule_store import (
    create_custom_rule,
    delete_custom_rule,
    get_all_rules,
    get_categories,
    get_rule,
    update_rule,
)

router = APIRouter(prefix="/api/rules", tags=["rules"])


@router.get("", response_model=list[Rule])
async def list_rules(
    category: Optional[str] = Query(None),
    enabled: Optional[bool] = Query(None),
):
    return get_all_rules(category=category, enabled=enabled)


@router.get("/categories", response_model=list[str])
async def list_categories():
    return get_categories()


@router.get("/{rule_id}", response_model=Rule)
async def get_rule_by_id(rule_id: str):
    rule = get_rule(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail=f"Rule '{rule_id}' not found.")
    return rule


@router.patch("/{rule_id}", response_model=Rule)
async def patch_rule(rule_id: str, updates: RuleUpdate):
    updated = update_rule(rule_id, updates)
    if not updated:
        raise HTTPException(status_code=404, detail=f"Rule '{rule_id}' not found.")
    return updated


@router.post("", response_model=Rule, status_code=201)
async def create_rule(data: RuleCreate):
    return create_custom_rule(data)


@router.delete("/{rule_id}", status_code=204)
async def delete_rule(rule_id: str):
    if not delete_custom_rule(rule_id):
        raise HTTPException(
            status_code=404,
            detail=f"Rule '{rule_id}' not found or is a built-in rule (cannot delete).",
        )
