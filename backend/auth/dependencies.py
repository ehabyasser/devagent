"""
backend/auth/dependencies.py

FastAPI dependency injection for authenticated routes.

Usage in route handlers:
    from backend.auth.dependencies import get_current_user, require_verified_user

    @router.get("/protected")
    async def endpoint(user: UserRecord = Depends(get_current_user)):
        ...
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import Cookie, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.auth.jwt_handler import decode_access_token
from backend.db.user_store import UserRecord, get_user_by_id

logger = logging.getLogger(__name__)

# HTTPBearer extractor — does NOT auto-raise 403 on missing header (auto_error=False)
# so we can return a proper 401 instead
_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> UserRecord:
    """
    Decode the Bearer token and return the authenticated UserRecord.
    Raises HTTP 401 if:
      - No token provided
      - Token is malformed or expired
      - User no longer exists in DB
    """
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated. Provide a valid Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_access_token(credentials.credentials)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is invalid or has expired.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id: Optional[str] = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed token payload.",
        )

    user = await get_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account not found.",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account has been deactivated. Contact support.",
        )

    return user


async def require_verified_user(
    user: UserRecord = Depends(get_current_user),
) -> UserRecord:
    """
    Like get_current_user but additionally requires email_verified=True.
    Use on routes that should only be accessible after email confirmation.
    """
    if not user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Please verify your email address before continuing.",
        )
    return user


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> Optional[UserRecord]:
    """
    Like get_current_user but returns None instead of raising 401.
    Use for endpoints that work for both authenticated and anonymous users.
    """
    if not credentials or not credentials.credentials:
        return None
    payload = decode_access_token(credentials.credentials)
    if not payload:
        return None
    user_id = payload.get("sub")
    if not user_id:
        return None
    return await get_user_by_id(user_id)
