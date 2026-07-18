"""
backend/db/database.py

Async SQLite connection manager via aiosqlite.

The database file location is resolved in priority order:
  1. DATABASE_PATH env var (e.g. /data/devagent.db on Render with a persistent disk)
  2. <project_root>/devagent.db  (local development default)

Usage:
    from backend.db.database import init_db, get_db

    # In FastAPI lifespan:
    await init_db()

    # In request handlers:
    async with get_db() as db:
        await db.execute(...)
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

import aiosqlite

# ── Resolve DB path ────────────────────────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_DB   = _PROJECT_ROOT / "devagent.db"
DB_PATH       = Path(os.getenv("DATABASE_PATH", str(_DEFAULT_DB)))


# ── Schema ─────────────────────────────────────────────────────────────────────
_CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS review_history (
    id              TEXT    PRIMARY KEY,          -- UUID
    pr_title        TEXT    NOT NULL,
    language        TEXT    NOT NULL DEFAULT 'swift',
    reviewed_at     TEXT    NOT NULL,             -- ISO-8601
    model_used      TEXT    NOT NULL,
    active_rules    INTEGER NOT NULL DEFAULT 0,

    -- Score snapshot (0-100 each)
    score_overall           INTEGER NOT NULL DEFAULT 0,
    score_security          INTEGER NOT NULL DEFAULT 0,
    score_architecture      INTEGER NOT NULL DEFAULT 0,
    score_performance       INTEGER NOT NULL DEFAULT 0,
    score_maintainability   INTEGER NOT NULL DEFAULT 0,
    score_readability       INTEGER NOT NULL DEFAULT 0,
    score_testing           INTEGER NOT NULL DEFAULT 0,
    score_production        INTEGER NOT NULL DEFAULT 0,

    violation_count INTEGER NOT NULL DEFAULT 0,
    approved        INTEGER NOT NULL DEFAULT 0,   -- BOOLEAN (0/1)
    approved_reason TEXT    NOT NULL DEFAULT '',

    -- Stored as JSON strings
    violations_json TEXT    NOT NULL DEFAULT '[]',
    summary         TEXT    NOT NULL DEFAULT '',

    -- First 500 chars of the diff (for preview only)
    diff_preview    TEXT    NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_review_history_reviewed_at
    ON review_history(reviewed_at DESC);
"""


async def init_db() -> None:
    """Create the database and tables if they don't exist yet."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(_CREATE_TABLES_SQL)
        await db.commit()


@asynccontextmanager
async def get_db() -> AsyncGenerator[aiosqlite.Connection, None]:
    """Async context manager that yields an open, row-factory-configured connection."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        yield db
