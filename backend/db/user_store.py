"""
backend/db/user_store.py

All database operations for users and authentication tokens.

All functions are async and use get_db() internally.
Uses dataclasses (not Pydantic) to avoid coupling DB layer to API layer.
"""
from __future__ import annotations

import hashlib
import logging
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from backend.db.database import get_db

logger = logging.getLogger(__name__)


# ── Data Models (DB layer — not exposed in API) ────────────────────────────────

@dataclass
class UserRecord:
    id: str
    email: str
    hashed_password: str
    full_name: str
    is_active: bool
    is_superuser: bool
    email_verified: bool
    avatar_url: Optional[str]
    failed_login_count: int
    locked_until: Optional[str]
    created_at: str
    updated_at: str
    last_login_at: Optional[str]


@dataclass
class EmailVerificationToken:
    id: str
    user_id: str
    token: str
    expires_at: str
    used_at: Optional[str]
    created_at: str


@dataclass
class PasswordResetToken:
    id: str
    user_id: str
    token: str
    expires_at: str
    used_at: Optional[str]
    created_at: str


@dataclass
class RefreshTokenRecord:
    id: str
    user_id: str
    token_hash: str
    expires_at: str
    revoked_at: Optional[str]
    device_hint: Optional[str]
    ip_address: Optional[str]
    created_at: str


# ── Helpers ────────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _expires(*, hours: int = 0, days: int = 0, minutes: int = 0) -> str:
    return (
        datetime.now(timezone.utc)
        + timedelta(hours=hours, days=days, minutes=minutes)
    ).isoformat()


def _hash_token(token: str) -> str:
    """SHA-256 hash of a token string (for safe storage)."""
    return hashlib.sha256(token.encode()).hexdigest()


def _row_to_user(row) -> Optional[UserRecord]:
    if row is None:
        return None
    return UserRecord(
        id=row["id"],
        email=row["email"],
        hashed_password=row["hashed_password"],
        full_name=row["full_name"] or "",
        is_active=bool(row["is_active"]),
        is_superuser=bool(row["is_superuser"]),
        email_verified=bool(row["email_verified"]),
        avatar_url=row["avatar_url"],
        failed_login_count=row["failed_login_count"],
        locked_until=row["locked_until"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        last_login_at=row["last_login_at"],
    )


# ── User CRUD ──────────────────────────────────────────────────────────────────

async def create_user(
    *,
    email: str,
    hashed_password: str,
    full_name: str = "",
    email_verified: bool = False,
    is_active: bool = True,
) -> UserRecord:
    now = _now()
    user_id = str(uuid.uuid4())
    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO users
              (id, email, hashed_password, full_name, is_active, is_superuser,
               email_verified, avatar_url, failed_login_count, locked_until,
               created_at, updated_at, last_login_at)
            VALUES (?, ?, ?, ?, ?, 0, ?, NULL, 0, NULL, ?, ?, NULL)
            """,
            (user_id, email.lower().strip(), hashed_password, full_name,
             1 if is_active else 0, 1 if email_verified else 0, now, now),
        )
        await db.commit()

    result = await get_user_by_id(user_id)
    if not result:
        raise RuntimeError("User creation failed silently.")
    return result


async def get_user_by_email(email: str) -> Optional[UserRecord]:
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM users WHERE email = ?", (email.lower().strip(),)
        )
        row = await cursor.fetchone()
    return _row_to_user(row)


async def get_user_by_id(user_id: str) -> Optional[UserRecord]:
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        )
        row = await cursor.fetchone()
    return _row_to_user(row)


async def update_user(user_id: str, **kwargs) -> Optional[UserRecord]:
    """Update arbitrary user fields. Only known columns are allowed."""
    allowed = {
        "full_name", "hashed_password", "is_active", "email_verified",
        "avatar_url", "failed_login_count", "locked_until", "last_login_at",
        "is_superuser",
    }
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return await get_user_by_id(user_id)

    updates["updated_at"] = _now()
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [user_id]

    async with get_db() as db:
        await db.execute(
            f"UPDATE users SET {set_clause} WHERE id = ?", values
        )
        await db.commit()

    return await get_user_by_id(user_id)


async def verify_user_email(user_id: str) -> None:
    await update_user(user_id, email_verified=True, is_active=True)


async def record_login_success(user_id: str) -> None:
    """Clear failed login counter and update last_login_at."""
    await update_user(
        user_id,
        failed_login_count=0,
        locked_until=None,
        last_login_at=_now(),
    )


async def record_login_failure(user: UserRecord) -> None:
    """
    Increment failed login count.
    Lock the account for 15 minutes after 10 consecutive failures.
    """
    new_count = user.failed_login_count + 1
    locked_until = None
    if new_count >= 10:
        locked_until = _expires(minutes=15)

    await update_user(
        user.id,
        failed_login_count=new_count,
        locked_until=locked_until,
    )


def is_account_locked(user: UserRecord) -> bool:
    if not user.locked_until:
        return False
    lock_time = datetime.fromisoformat(user.locked_until)
    return datetime.now(timezone.utc) < lock_time


# ── Email Verification Tokens ──────────────────────────────────────────────────

async def create_email_verification_token(user_id: str) -> str:
    """Create a new email verification token. Returns the raw (unhashed) token."""
    token = secrets.token_hex(32)   # 64-char hex string
    token_id = str(uuid.uuid4())
    now = _now()
    expires = _expires(hours=24)

    async with get_db() as db:
        # Invalidate any existing unused tokens for this user
        await db.execute(
            "DELETE FROM email_verification_tokens WHERE user_id = ? AND used_at IS NULL",
            (user_id,),
        )
        await db.execute(
            """
            INSERT INTO email_verification_tokens
              (id, user_id, token, expires_at, used_at, created_at)
            VALUES (?, ?, ?, ?, NULL, ?)
            """,
            (token_id, user_id, token, expires, now),
        )
        await db.commit()

    return token


async def get_email_verification_token(token: str) -> Optional[EmailVerificationToken]:
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM email_verification_tokens WHERE token = ?", (token,)
        )
        row = await cursor.fetchone()
    if not row:
        return None
    return EmailVerificationToken(
        id=row["id"],
        user_id=row["user_id"],
        token=row["token"],
        expires_at=row["expires_at"],
        used_at=row["used_at"],
        created_at=row["created_at"],
    )


async def mark_email_token_used(token_id: str) -> None:
    async with get_db() as db:
        await db.execute(
            "UPDATE email_verification_tokens SET used_at = ? WHERE id = ?",
            (_now(), token_id),
        )
        await db.commit()


# ── Password Reset Tokens ──────────────────────────────────────────────────────

async def create_password_reset_token(user_id: str) -> str:
    """Create a password reset token (1 hour TTL). Returns raw token."""
    token = secrets.token_hex(32)
    token_id = str(uuid.uuid4())
    now = _now()
    expires = _expires(hours=1)

    async with get_db() as db:
        # Invalidate any existing unused reset tokens
        await db.execute(
            "DELETE FROM password_reset_tokens WHERE user_id = ? AND used_at IS NULL",
            (user_id,),
        )
        await db.execute(
            """
            INSERT INTO password_reset_tokens
              (id, user_id, token, expires_at, used_at, created_at)
            VALUES (?, ?, ?, ?, NULL, ?)
            """,
            (token_id, user_id, token, expires, now),
        )
        await db.commit()

    return token


async def get_password_reset_token(token: str) -> Optional[PasswordResetToken]:
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM password_reset_tokens WHERE token = ?", (token,)
        )
        row = await cursor.fetchone()
    if not row:
        return None
    return PasswordResetToken(
        id=row["id"],
        user_id=row["user_id"],
        token=row["token"],
        expires_at=row["expires_at"],
        used_at=row["used_at"],
        created_at=row["created_at"],
    )


async def mark_reset_token_used(token_id: str) -> None:
    async with get_db() as db:
        await db.execute(
            "UPDATE password_reset_tokens SET used_at = ? WHERE id = ?",
            (_now(), token_id),
        )
        await db.commit()


# ── Refresh Tokens ─────────────────────────────────────────────────────────────

async def create_refresh_token(
    user_id: str,
    *,
    device_hint: Optional[str] = None,
    ip_address: Optional[str] = None,
    expire_days: int = 30,
) -> str:
    """
    Create a new refresh token. Stores only the SHA-256 hash.
    Returns the raw token (sent to client as HttpOnly cookie).
    """
    from backend.config import settings
    expire_days = settings.refresh_token_expire_days

    raw_token = secrets.token_hex(40)   # 80-char hex, 320 bits of entropy
    token_hash = _hash_token(raw_token)
    token_id = str(uuid.uuid4())
    now = _now()
    expires = _expires(days=expire_days)

    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO refresh_tokens
              (id, user_id, token_hash, expires_at, revoked_at,
               device_hint, ip_address, created_at)
            VALUES (?, ?, ?, ?, NULL, ?, ?, ?)
            """,
            (token_id, user_id, token_hash, expires, device_hint, ip_address, now),
        )
        await db.commit()

    return raw_token


async def get_refresh_token(raw_token: str) -> Optional[RefreshTokenRecord]:
    """Look up a refresh token by its raw value (hashed internally)."""
    token_hash = _hash_token(raw_token)
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM refresh_tokens WHERE token_hash = ?", (token_hash,)
        )
        row = await cursor.fetchone()
    if not row:
        return None
    return RefreshTokenRecord(
        id=row["id"],
        user_id=row["user_id"],
        token_hash=row["token_hash"],
        expires_at=row["expires_at"],
        revoked_at=row["revoked_at"],
        device_hint=row["device_hint"],
        ip_address=row["ip_address"],
        created_at=row["created_at"],
    )


async def revoke_refresh_token(token_id: str) -> None:
    async with get_db() as db:
        await db.execute(
            "UPDATE refresh_tokens SET revoked_at = ? WHERE id = ?",
            (_now(), token_id),
        )
        await db.commit()


async def revoke_all_user_refresh_tokens(user_id: str) -> None:
    """Revoke all active sessions for a user (used on password change)."""
    async with get_db() as db:
        await db.execute(
            "UPDATE refresh_tokens SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL",
            (_now(), user_id),
        )
        await db.commit()


def is_refresh_token_valid(rt: RefreshTokenRecord) -> bool:
    """Returns True if the token is active and not expired."""
    if rt.revoked_at is not None:
        return False
    expires = datetime.fromisoformat(rt.expires_at)
    return datetime.now(timezone.utc) < expires
