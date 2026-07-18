"""
backend/auth/jwt_handler.py

JWT access token creation and decoding using python-jose.

Access tokens:
  - Algorithm: HS256
  - Payload: sub (user_id), email, exp, iat, type="access"
  - Expiry: configurable (default 15 minutes)
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt

from backend.config import settings

logger = logging.getLogger(__name__)

_ALGORITHM = settings.jwt_algorithm


def create_access_token(*, user_id: str, email: str) -> str:
    """
    Create a signed JWT access token.
    Payload includes: sub, email, iat, exp, type.
    """
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": user_id,
        "email": email,
        "iat": now,
        "exp": expire,
        "type": "access",
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=_ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    """
    Decode and validate a JWT access token.
    Returns the payload dict, or None if the token is invalid/expired.
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[_ALGORITHM],
        )
        if payload.get("type") != "access":
            return None
        return payload
    except JWTError as exc:
        logger.debug("JWT decode failed: %s", exc)
        return None
