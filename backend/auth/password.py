"""
backend/auth/password.py

Password hashing and verification using bcrypt directly.
bcrypt is intentionally slow — this is a security feature, not a bug.

Note: Using `bcrypt` package directly (not via passlib) for Python 3.9 + bcrypt 5.x compatibility.
"""
from __future__ import annotations

import re
from typing import Optional

import bcrypt

# Work factor 12 — good balance of security vs. performance (~300ms per hash)
_ROUNDS = 12

# Password strength rules
_MIN_LENGTH = 8
_PASSWORD_RE = re.compile(r"^(?=.*[A-Za-z])(?=.*\d).{8,}$")


def hash_password(plain: str) -> str:
    """Return a bcrypt hash of the plain-text password."""
    salt = bcrypt.gensalt(rounds=_ROUNDS)
    return bcrypt.hashpw(plain.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """
    Return True if plain matches the hashed password.
    bcrypt.checkpw is constant-time — safe against timing attacks.
    """
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def validate_password_strength(password: str) -> Optional[str]:
    """
    Validate password strength.
    Returns an error message string, or None if the password is acceptable.
    """
    if len(password) < _MIN_LENGTH:
        return f"Password must be at least {_MIN_LENGTH} characters long."
    if not _PASSWORD_RE.match(password):
        return "Password must contain at least one letter and one number."
    return None


def safe_verify(plain: str, hashed: Optional[str]) -> bool:
    """
    Verify password, using a dummy hash if no real hash is provided.
    Ensures constant-time behaviour regardless of whether the user exists.
    """
    if hashed is None:
        # Always do a verify call to prevent timing-based user enumeration
        _dummy = "$2b$12$aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa."
        bcrypt.checkpw(b"dummy", _dummy.encode("utf-8"))
        return False
    return verify_password(plain, hashed)
