"""
backend/db/migrations/m001_auth_tables.py

Migration 001: Create authentication tables.

Tables created:
  - users                      Core user accounts
  - email_verification_tokens  One-time email verification links
  - password_reset_tokens      One-time password reset links
  - refresh_tokens             Persistent session tokens (stored as hash)
"""
from __future__ import annotations

import aiosqlite


_SQL_UP = """
-- ── Users ─────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id                  TEXT    PRIMARY KEY,          -- UUID v4
    email               TEXT    UNIQUE NOT NULL,
    hashed_password     TEXT    NOT NULL,
    full_name           TEXT    NOT NULL DEFAULT '',
    is_active           INTEGER NOT NULL DEFAULT 1,  -- 1 = can log in
    is_superuser        INTEGER NOT NULL DEFAULT 0,  -- admin flag
    email_verified      INTEGER NOT NULL DEFAULT 0,
    avatar_url          TEXT,
    failed_login_count  INTEGER NOT NULL DEFAULT 0,
    locked_until        TEXT,                        -- ISO-8601, NULL if not locked
    created_at          TEXT    NOT NULL,
    updated_at          TEXT    NOT NULL,
    last_login_at       TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email
    ON users(email);

-- ── Email Verification Tokens ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS email_verification_tokens (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token       TEXT UNIQUE NOT NULL,                -- random 64-char hex
    expires_at  TEXT NOT NULL,                       -- 24 hours from creation
    used_at     TEXT,                               -- NULL until used
    created_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_evtokens_user_id
    ON email_verification_tokens(user_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_evtokens_token
    ON email_verification_tokens(token);

-- ── Password Reset Tokens ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token       TEXT UNIQUE NOT NULL,                -- random 64-char hex
    expires_at  TEXT NOT NULL,                       -- 1 hour from creation
    used_at     TEXT,                               -- NULL until used
    created_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_prtokens_user_id
    ON password_reset_tokens(user_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_prtokens_token
    ON password_reset_tokens(token);

-- ── Refresh Tokens ────────────────────────────────────────────────────────────
-- The actual token value is NEVER stored — only its SHA-256 hash.
CREATE TABLE IF NOT EXISTS refresh_tokens (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash  TEXT UNIQUE NOT NULL,               -- SHA-256(raw_token)
    expires_at  TEXT NOT NULL,
    revoked_at  TEXT,                               -- NULL = active session
    device_hint TEXT,                               -- e.g. "Chrome on macOS"
    ip_address  TEXT,
    created_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_rftokens_user_id   ON refresh_tokens(user_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_rftokens_hash ON refresh_tokens(token_hash);
"""

_SQL_DOWN = """
DROP INDEX IF EXISTS idx_rftokens_hash;
DROP INDEX IF EXISTS idx_rftokens_user_id;
DROP TABLE IF EXISTS refresh_tokens;
DROP INDEX IF EXISTS idx_prtokens_token;
DROP INDEX IF EXISTS idx_prtokens_user_id;
DROP TABLE IF EXISTS password_reset_tokens;
DROP INDEX IF EXISTS idx_evtokens_token;
DROP INDEX IF EXISTS idx_evtokens_user_id;
DROP TABLE IF EXISTS email_verification_tokens;
DROP INDEX IF EXISTS idx_users_email;
DROP TABLE IF EXISTS users;
"""


async def upgrade(db: aiosqlite.Connection) -> None:
    await db.executescript(_SQL_UP)


async def downgrade(db: aiosqlite.Connection) -> None:
    await db.executescript(_SQL_DOWN)
