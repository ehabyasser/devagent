"""
backend/tests/test_auth.py

Integration tests for the authentication system.
Uses an isolated temp SQLite database.
"""
from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

import pytest

# ── Isolate DB before any imports touch the module ────────────────────────────
_TMP_DB = tempfile.mktemp(suffix="_test_auth.db")
os.environ["DATABASE_PATH"] = _TMP_DB
os.environ["JWT_SECRET"] = "test-secret-key-32-characters-long-enough"
os.environ["EMAIL_VERIFICATION_ENABLED"] = "false"
os.environ["LLM_PROVIDER"] = "mock"

import backend.db.database as _db_mod
_db_mod.DB_PATH = Path(_TMP_DB)

from backend.db.database import init_db
from backend.db.user_store import (
    create_user,
    get_user_by_email,
    get_user_by_id,
    create_refresh_token,
    get_refresh_token,
    is_refresh_token_valid,
    revoke_refresh_token,
    create_email_verification_token,
    get_email_verification_token,
    mark_email_token_used,
    create_password_reset_token,
    get_password_reset_token,
)
from backend.auth.password import hash_password, verify_password, validate_password_strength
from backend.auth.jwt_handler import create_access_token, decode_access_token


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True, scope="module")
def setup_database():
    loop = asyncio.new_event_loop()
    loop.run_until_complete(init_db())
    yield
    loop.close()
    Path(_TMP_DB).unlink(missing_ok=True)


# ── Password tests ─────────────────────────────────────────────────────────────

def test_password_hash_and_verify():
    hashed = hash_password("MySecure1!")
    assert hashed != "MySecure1!"
    assert verify_password("MySecure1!", hashed)
    assert not verify_password("WrongPass1!", hashed)


def test_password_strength_valid():
    assert validate_password_strength("MyPass123") is None
    assert validate_password_strength("aB3!defgh") is None


def test_password_strength_too_short():
    error = validate_password_strength("Abc1")
    assert error is not None
    assert "8" in error


def test_password_strength_no_number():
    error = validate_password_strength("OnlyLetters!")
    assert error is not None


# ── JWT tests ──────────────────────────────────────────────────────────────────

def test_jwt_create_and_decode():
    token = create_access_token(user_id="user-123", email="test@test.com")
    assert isinstance(token, str)
    assert len(token) > 50

    payload = decode_access_token(token)
    assert payload is not None
    assert payload["sub"] == "user-123"
    assert payload["email"] == "test@test.com"
    assert payload["type"] == "access"


def test_jwt_invalid_token():
    payload = decode_access_token("not.a.valid.token")
    assert payload is None


def test_jwt_tampered_token():
    token = create_access_token(user_id="abc", email="x@x.com")
    tampered = token[:-5] + "XXXXX"
    assert decode_access_token(tampered) is None


# ── User store tests ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_user_success():
    hashed = hash_password("SecurePass1!")
    user = await create_user(
        email="alice@example.com",
        hashed_password=hashed,
        full_name="Alice Test",
        email_verified=True,
    )
    assert user.id is not None
    assert user.email == "alice@example.com"
    assert user.full_name == "Alice Test"
    assert user.email_verified is True
    assert user.is_active is True
    assert user.is_superuser is False


@pytest.mark.asyncio
async def test_get_user_by_email():
    user = await get_user_by_email("alice@example.com")
    assert user is not None
    assert user.email == "alice@example.com"


@pytest.mark.asyncio
async def test_get_user_by_email_not_found():
    user = await get_user_by_email("nobody@nowhere.com")
    assert user is None


@pytest.mark.asyncio
async def test_email_normalisation():
    # Emails should be stored lowercase
    hashed = hash_password("SecurePass1!")
    user = await create_user(
        email="  BOB@EXAMPLE.COM  ",
        hashed_password=hashed,
    )
    assert user.email == "bob@example.com"
    found = await get_user_by_email("BOB@EXAMPLE.COM")
    assert found is not None
    assert found.id == user.id


# ── Refresh token tests ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_refresh_token_lifecycle():
    hashed = hash_password("SecurePass1!")
    user = await create_user(email="rt-test@example.com", hashed_password=hashed)

    raw = await create_refresh_token(user.id, device_hint="Chrome on macOS")
    assert len(raw) == 80  # 40 bytes hex = 80 chars

    rt = await get_refresh_token(raw)
    assert rt is not None
    assert rt.user_id == user.id
    assert rt.device_hint == "Chrome on macOS"
    assert is_refresh_token_valid(rt) is True


@pytest.mark.asyncio
async def test_refresh_token_revocation():
    hashed = hash_password("SecurePass1!")
    user = await create_user(email="rt-revoke@example.com", hashed_password=hashed)

    raw = await create_refresh_token(user.id)
    rt = await get_refresh_token(raw)
    assert rt is not None

    await revoke_refresh_token(rt.id)

    rt_revoked = await get_refresh_token(raw)
    assert rt_revoked is not None
    assert is_refresh_token_valid(rt_revoked) is False


@pytest.mark.asyncio
async def test_refresh_token_invalid_raw():
    rt = await get_refresh_token("completely-invalid-token-that-doesnt-exist")
    assert rt is None


# ── Email verification token tests ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_email_verification_token_lifecycle():
    hashed = hash_password("SecurePass1!")
    user = await create_user(email="ev-test@example.com", hashed_password=hashed)

    token_str = await create_email_verification_token(user.id)
    assert len(token_str) == 64  # 32 bytes = 64 hex chars

    record = await get_email_verification_token(token_str)
    assert record is not None
    assert record.user_id == user.id
    assert record.used_at is None


@pytest.mark.asyncio
async def test_email_verification_token_single_use():
    hashed = hash_password("SecurePass1!")
    user = await create_user(email="ev-singleuse@example.com", hashed_password=hashed)

    token_str = await create_email_verification_token(user.id)
    record = await get_email_verification_token(token_str)
    await mark_email_token_used(record.id)

    # Second lookup should still return the record — but used_at will be set
    record2 = await get_email_verification_token(token_str)
    assert record2 is not None
    assert record2.used_at is not None


# ── Password reset token tests ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_password_reset_token_lifecycle():
    hashed = hash_password("SecurePass1!")
    user = await create_user(email="pr-test@example.com", hashed_password=hashed)

    token_str = await create_password_reset_token(user.id)
    assert len(token_str) == 64

    record = await get_password_reset_token(token_str)
    assert record is not None
    assert record.user_id == user.id
    assert record.used_at is None


@pytest.mark.asyncio
async def test_password_reset_token_not_found():
    record = await get_password_reset_token("a" * 64)
    assert record is None
