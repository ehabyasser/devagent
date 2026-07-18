"""
backend/db/database.py

Async SQLite connection manager via aiosqlite.

Database file location priority:
  1. DATABASE_PATH env var (e.g. /data/devagent.db on Render with a persistent disk)
  2. <project_root>/devagent.db  (local development default)

On startup, call init_db() to:
  1. Enable WAL mode (better concurrent read/write performance)
  2. Run pending schema migrations

Usage:
    from backend.db.database import init_db, get_db

    await init_db()   # once at app startup

    async with get_db() as db:
        await db.execute(...)
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

import aiosqlite

logger = logging.getLogger(__name__)

# ── Resolve DB path ────────────────────────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_DB   = _PROJECT_ROOT / "devagent.db"
DB_PATH       = Path(os.getenv("DATABASE_PATH", str(_DEFAULT_DB)))


# ── Legacy tables (created directly, before migration system was introduced) ──
_LEGACY_DDL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
PRAGMA busy_timeout=5000;

CREATE TABLE IF NOT EXISTS review_history (
    id              TEXT    PRIMARY KEY,
    pr_title        TEXT    NOT NULL,
    language        TEXT    NOT NULL DEFAULT 'swift',
    reviewed_at     TEXT    NOT NULL,
    model_used      TEXT    NOT NULL,
    active_rules    INTEGER NOT NULL DEFAULT 0,
    score_overall           INTEGER NOT NULL DEFAULT 0,
    score_security          INTEGER NOT NULL DEFAULT 0,
    score_architecture      INTEGER NOT NULL DEFAULT 0,
    score_performance       INTEGER NOT NULL DEFAULT 0,
    score_maintainability   INTEGER NOT NULL DEFAULT 0,
    score_readability       INTEGER NOT NULL DEFAULT 0,
    score_testing           INTEGER NOT NULL DEFAULT 0,
    score_production        INTEGER NOT NULL DEFAULT 0,
    violation_count INTEGER NOT NULL DEFAULT 0,
    approved        INTEGER NOT NULL DEFAULT 0,
    approved_reason TEXT    NOT NULL DEFAULT '',
    violations_json TEXT    NOT NULL DEFAULT '[]',
    summary         TEXT    NOT NULL DEFAULT '',
    diff_preview    TEXT    NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_review_history_reviewed_at
    ON review_history(reviewed_at DESC);
"""


async def init_db() -> None:
    """
    Initialise the database:
      1. Create DB file and parent directories if needed
      2. Run legacy DDL (review_history table — created before migration system)
      3. Run all pending schema migrations via the migration runner
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Step 1 & 2: legacy tables
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(_LEGACY_DDL)
        await db.commit()

    # Step 3: versioned migrations
    from backend.db.migrations.runner import run_migrations
    await run_migrations()

    logger.info("Database ready: %s", DB_PATH)


@asynccontextmanager
async def get_db() -> AsyncGenerator[aiosqlite.Connection, None]:
    """
    Async context manager that yields an open SQLite connection.
    Row factory is set to aiosqlite.Row for dict-like access.
    Foreign keys and busy timeout are enabled per connection.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys=ON")
        await db.execute("PRAGMA busy_timeout=5000")
        yield db
