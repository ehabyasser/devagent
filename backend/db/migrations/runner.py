"""
backend/db/migrations/runner.py

Lightweight async migration runner using aiosqlite.

Tracks applied migrations in a `schema_versions` table.
Each migration is a Python module with `upgrade(db)` and `downgrade(db)` coroutines.

Usage:
    from backend.db.migrations.runner import run_migrations
    await run_migrations()   # called once at startup in init_db()
"""
from __future__ import annotations

import importlib
import logging
from datetime import datetime, timezone
from typing import List, Tuple

import aiosqlite

from backend.db.database import get_db

logger = logging.getLogger(__name__)

# ── Registry — add new migrations here in order ───────────────────────────────
# Format: (version_id, display_name, module_path)
MIGRATION_REGISTRY: List[Tuple[str, str, str]] = [
    ("001", "auth_tables", "backend.db.migrations.m001_auth_tables"),
]

_SCHEMA_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS schema_versions (
    version     TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    applied_at  TEXT NOT NULL
);
"""


async def run_migrations() -> None:
    """
    Apply all pending migrations in order.
    Idempotent — safe to call on every startup.
    """
    async with get_db() as db:
        # Ensure the version tracking table exists
        await db.execute(_SCHEMA_TABLE_SQL)
        await db.commit()

        # Fetch already-applied migrations
        cursor = await db.execute("SELECT version FROM schema_versions")
        rows = await cursor.fetchall()
        applied = {row[0] for row in rows}

        # Apply pending migrations
        for version, name, module_path in MIGRATION_REGISTRY:
            if version in applied:
                logger.debug("Migration %s (%s) already applied — skipping.", version, name)
                continue

            logger.info("Applying migration %s: %s …", version, name)
            try:
                module = importlib.import_module(module_path)
                await module.upgrade(db)
                now = datetime.now(timezone.utc).isoformat()
                await db.execute(
                    "INSERT INTO schema_versions (version, name, applied_at) VALUES (?, ?, ?)",
                    (version, name, now),
                )
                await db.commit()
                logger.info("✓ Migration %s (%s) applied successfully.", version, name)
            except Exception as exc:
                logger.error("✗ Migration %s (%s) failed: %s", version, name, exc)
                raise
