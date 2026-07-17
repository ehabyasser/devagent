"""
backend/rules/rule_store.py

File-based rule store. Rules live in rules/builtin/*.json and rules/custom/*.json.
No database required — rules can be version-controlled with Git.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .rule_schema import Rule, RuleCreate, RuleUpdate

# Resolve paths relative to project root (two levels up from this file)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
RULES_BUILTIN_DIR = _PROJECT_ROOT / "rules" / "builtin"
RULES_CUSTOM_DIR = _PROJECT_ROOT / "rules" / "custom"


def _load_json_file(path: Path) -> list[dict]:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_json_file(path: Path, data: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _load_all_rules() -> list[Rule]:
    rules: list[Rule] = []

    # Load builtin rules
    for json_file in sorted(RULES_BUILTIN_DIR.glob("*.json")):
        for raw in _load_json_file(json_file):
            try:
                rules.append(Rule.model_validate(raw))
            except Exception:
                continue

    # Load custom rules
    for json_file in sorted(RULES_CUSTOM_DIR.glob("*.json")):
        for raw in _load_json_file(json_file):
            try:
                rules.append(Rule.model_validate(raw))
            except Exception:
                continue

    return rules


def get_all_rules(
    category: Optional[str] = None,
    enabled: Optional[bool] = None,
) -> list[Rule]:
    rules = _load_all_rules()
    if category:
        rules = [r for r in rules if r.category == category]
    if enabled is not None:
        rules = [r for r in rules if r.enabled == enabled]
    return rules


def get_rule(rule_id: str) -> Optional[Rule]:
    for rule in _load_all_rules():
        if rule.id == rule_id:
            return rule
    return None


def update_rule(rule_id: str, updates: RuleUpdate) -> Optional[Rule]:
    """
    Update a rule in its source JSON file.
    Works for both builtin and custom rules.
    """
    # Find which file contains this rule
    for search_dir in [RULES_BUILTIN_DIR, RULES_CUSTOM_DIR]:
        for json_file in search_dir.glob("*.json"):
            rules_raw = _load_json_file(json_file)
            for i, raw in enumerate(rules_raw):
                if raw.get("id") == rule_id:
                    # Apply updates
                    patch = updates.model_dump(exclude_none=True)
                    patch["updated_at"] = datetime.now(timezone.utc).isoformat()
                    if "examples" in patch and isinstance(patch["examples"], dict):
                        pass  # already a dict
                    raw.update(patch)
                    rules_raw[i] = raw
                    _save_json_file(json_file, rules_raw)
                    return Rule.model_validate(raw)
    return None


def create_custom_rule(data: RuleCreate) -> Rule:
    """Create a new custom rule saved to rules/custom/custom_rules.json."""
    custom_file = RULES_CUSTOM_DIR / "custom_rules.json"
    existing = _load_json_file(custom_file)

    # Generate a unique ID
    rule_id = f"CUSTOM-{uuid.uuid4().hex[:6].upper()}"
    now = datetime.now(timezone.utc).isoformat()

    raw = {
        "id": rule_id,
        "custom": True,
        "created_at": now,
        "updated_at": now,
        **data.model_dump(),
    }
    # Serialize nested examples
    if isinstance(raw.get("examples"), object) and hasattr(raw["examples"], "model_dump"):
        raw["examples"] = raw["examples"].model_dump()

    existing.append(raw)
    _save_json_file(custom_file, existing)
    return Rule.model_validate(raw)


def delete_custom_rule(rule_id: str) -> bool:
    """Only custom rules can be deleted."""
    custom_file = RULES_CUSTOM_DIR / "custom_rules.json"
    existing = _load_json_file(custom_file)
    filtered = [r for r in existing if r.get("id") != rule_id]
    if len(filtered) == len(existing):
        return False
    _save_json_file(custom_file, filtered)
    return True


def get_categories() -> list[str]:
    return sorted({r.category for r in _load_all_rules()})
