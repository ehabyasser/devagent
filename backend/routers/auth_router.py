"""
backend/routers/auth_router.py

Authentication API — all /api/auth/* endpoints.

POST   /api/auth/signup                Create account
POST   /api/auth/verify-email          Verify email with token
POST   /api/auth/resend-verification   Resend verification email
POST   /api/auth/login                 Login → access token + refresh cookie
POST   /api/auth/refresh               Rotate refresh token → new access token
POST   /api/auth/logout                Revoke refresh token
POST   /api/auth/forgot-password       Send password reset email
POST   /api/auth/reset-password        Reset password with token
GET    /api/auth/me                    Get current user profile
PATCH  /api/auth/me                    Update profile
PATCH  /api/auth/me/password           Change password
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status

from backend.auth.dependencies import get_current_user
from backend.auth.email_service import send_password_reset_email, send_verification_email
from backend.auth.jwt_handler import create_access_token
from backend.auth.password import hash_password, safe_verify, validate_password_strength
from backend.config import settings
from backend.core.limiter import limiter
from backend.db.user_store import (
    UserRecord,
    create_email_verification_token,
    create_password_reset_token,
    create_refresh_token,
    create_user,
    get_email_verification_token,
    get_password_reset_token,
    get_refresh_token,
    get_user_by_email,
    get_user_by_id,
    is_account_locked,
    is_refresh_token_valid,
    mark_email_token_used,
    mark_reset_token_used,
    record_login_failure,
    record_login_success,
    revoke_all_user_refresh_tokens,
    revoke_refresh_token,
    update_user,
    verify_user_email,
)
from backend.schemas.auth import (
    AccessTokenResponse,
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    ResendVerificationRequest,
    ResetPasswordRequest,
    SignupRequest,
    TokenResponse,
    UpdateProfileRequest,
    UserResponse,
    VerifyEmailRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Cookie config — centralised for consistency
_REFRESH_COOKIE_NAME = "refresh_token"
_REFRESH_MAX_AGE = settings.refresh_token_expire_days * 24 * 60 * 60  # seconds


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=_REFRESH_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        max_age=_REFRESH_MAX_AGE,
        domain=settings.cookie_domain,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=_REFRESH_COOKIE_NAME,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
    )


def _get_device_hint(request: Request) -> str:
    ua = request.headers.get("user-agent", "")
    # Very simple browser/OS extraction — good enough for session display
    parts = []
    for browser in ("Chrome", "Firefox", "Safari", "Edge"):
        if browser in ua:
            parts.append(browser)
            break
    for os_name in ("Windows", "Mac OS", "Linux", "Android", "iOS"):
        if os_name in ua:
            parts.append(os_name)
            break
    return " on ".join(parts) if parts else "Unknown device"


def _make_token_response(user: UserRecord, access_token: str) -> dict:
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": settings.access_token_expire_minutes * 60,
        "user": UserResponse.from_record(user),
    }


# ── SIGNUP ─────────────────────────────────────────────────────────────────────

@router.post("/signup", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(settings.rate_limit_signup)
async def signup(request: Request, body: SignupRequest) -> MessageResponse:
    """
    Create a new user account.
    If EMAIL_VERIFICATION_ENABLED is True, account is inactive until email is verified.
    If disabled (dev/testing), account is immediately active.
    """
    # Check for duplicate email
    existing = await get_user_by_email(body.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email address already exists.",
        )

    hashed = hash_password(body.password)
    verification_required = settings.email_verification_enabled

    user = await create_user(
        email=body.email,
        hashed_password=hashed,
        full_name=body.full_name,
        email_verified=not verification_required,
        is_active=True,  # always active — verification is a soft gate
    )

    if verification_required:
        token = await create_email_verification_token(user.id)
        try:
            await send_verification_email(user.email, token)
        except Exception as exc:
            logger.error("Failed to send verification email: %s", exc)
            # Don't fail signup if email sending fails — user can resend

        return MessageResponse(
            message="Account created! Please check your email to verify your address before signing in."
        )
    else:
        return MessageResponse(
            message="Account created successfully. You can now sign in."
        )


# ── EMAIL VERIFICATION ─────────────────────────────────────────────────────────

@router.post("/verify-email", response_model=MessageResponse)
async def verify_email(body: VerifyEmailRequest) -> MessageResponse:
    """Verify email address using the token from the verification email."""
    record = await get_email_verification_token(body.token)

    if not record or record.used_at is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This verification link is invalid or has already been used.",
        )

    expires = datetime.fromisoformat(record.expires_at)
    if datetime.now(timezone.utc) > expires:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This verification link has expired. Please request a new one.",
        )

    await mark_email_token_used(record.id)
    await verify_user_email(record.user_id)

    return MessageResponse(message="Email verified successfully. You can now sign in.")


# ── RESEND VERIFICATION ────────────────────────────────────────────────────────

@router.post("/resend-verification", response_model=MessageResponse)
@limiter.limit("3/minute")
async def resend_verification(
    request: Request, body: ResendVerificationRequest
) -> MessageResponse:
    """Resend the email verification link. Always returns 200 to prevent email enumeration."""
    user = await get_user_by_email(body.email)
    if user and not user.email_verified:
        token = await create_email_verification_token(user.id)
        try:
            await send_verification_email(user.email, token)
        except Exception as exc:
            logger.error("Failed to resend verification email: %s", exc)

    # Always the same response — never reveal whether email exists
    return MessageResponse(
        message="If this email is registered and unverified, a new verification link has been sent."
    )


# ── LOGIN ──────────────────────────────────────────────────────────────────────

@router.post("/login", response_model=TokenResponse)
@limiter.limit(settings.rate_limit_login)
async def login(
    request: Request,
    response: Response,
    body: LoginRequest,
) -> dict:
    """
    Authenticate user and issue access token + refresh token cookie.

    Security:
    - safe_verify() always runs bcrypt even if user doesn't exist (timing attack prevention)
    - Account lockout after 10 failed attempts for 15 minutes
    - Refresh token stored as SHA-256 hash only
    """
    user = await get_user_by_email(body.email)

    # Run bcrypt regardless of whether user exists — prevent timing attacks
    is_valid = safe_verify(body.password, user.hashed_password if user else None)

    if not user or not is_valid:
        if user:
            await record_login_failure(user)
            # Re-fetch to check lockout after incrementing
            user = await get_user_by_id(user.id)
            if user and is_account_locked(user):
                raise HTTPException(
                    status_code=status.HTTP_423_LOCKED,
                    detail="Account temporarily locked due to too many failed attempts. Try again in 15 minutes.",
                )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    if is_account_locked(user):
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="Account temporarily locked due to too many failed attempts. Try again in 15 minutes.",
        )

    if settings.email_verification_enabled and not user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Please verify your email address before signing in. Check your inbox.",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account has been deactivated. Contact support.",
        )

    # Issue tokens
    access_token = create_access_token(user_id=user.id, email=user.email)
    raw_refresh = await create_refresh_token(
        user.id,
        device_hint=_get_device_hint(request),
        ip_address=request.client.host if request.client else None,
    )

    # Set HttpOnly refresh token cookie
    _set_refresh_cookie(response, raw_refresh)

    # Update last login timestamp
    await record_login_success(user.id)
    user = await get_user_by_id(user.id)  # re-fetch with updated last_login_at

    return _make_token_response(user, access_token)


# ── REFRESH TOKEN ──────────────────────────────────────────────────────────────

@router.post("/refresh", response_model=AccessTokenResponse)
async def refresh_token(
    request: Request,
    response: Response,
    refresh_token_cookie: Optional[str] = Cookie(default=None, alias="refresh_token"),
) -> dict:
    """
    Issue a new access token using the refresh token cookie.
    The refresh token is rotated (old one revoked, new one issued) on each use.
    """
    if not refresh_token_cookie:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No refresh token found. Please sign in.",
        )

    rt = await get_refresh_token(refresh_token_cookie)

    if not rt or not is_refresh_token_valid(rt):
        _clear_refresh_cookie(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token is invalid, expired, or revoked. Please sign in again.",
        )

    user = await get_user_by_id(rt.user_id)
    if not user or not user.is_active:
        _clear_refresh_cookie(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account not found or deactivated.",
        )

    # Rotate: revoke old token, issue new one
    await revoke_refresh_token(rt.id)
    new_raw_refresh = await create_refresh_token(
        user.id,
        device_hint=rt.device_hint,
        ip_address=request.client.host if request.client else None,
    )
    _set_refresh_cookie(response, new_raw_refresh)

    new_access = create_access_token(user_id=user.id, email=user.email)

    return {
        "access_token": new_access,
        "token_type": "bearer",
        "expires_in": settings.access_token_expire_minutes * 60,
    }


# ── LOGOUT ─────────────────────────────────────────────────────────────────────

@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def logout(
    response: Response,
    refresh_token_cookie: Optional[str] = Cookie(default=None, alias="refresh_token"),
) -> None:
    """Revoke the refresh token and clear the cookie. Always returns 204."""
    if refresh_token_cookie:
        rt = await get_refresh_token(refresh_token_cookie)
        if rt and is_refresh_token_valid(rt):
            await revoke_refresh_token(rt.id)
    _clear_refresh_cookie(response)


# ── FORGOT PASSWORD ────────────────────────────────────────────────────────────

@router.post("/forgot-password", response_model=MessageResponse)
@limiter.limit(settings.rate_limit_forgot)
async def forgot_password(
    request: Request, body: ForgotPasswordRequest
) -> MessageResponse:
    """Send a password reset email. Always returns 200 to prevent email enumeration."""
    user = await get_user_by_email(body.email)
    if user and user.is_active:
        token = await create_password_reset_token(user.id)
        try:
            await send_password_reset_email(user.email, token)
        except Exception as exc:
            logger.error("Failed to send password reset email: %s", exc)

    return MessageResponse(
        message="If this email is registered, a password reset link has been sent. Check your inbox."
    )


# ── RESET PASSWORD ─────────────────────────────────────────────────────────────

@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(body: ResetPasswordRequest) -> MessageResponse:
    """Reset user password using token from email. Token is single-use."""
    record = await get_password_reset_token(body.token)

    if not record or record.used_at is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This reset link is invalid or has already been used.",
        )

    expires = datetime.fromisoformat(record.expires_at)
    if datetime.now(timezone.utc) > expires:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This reset link has expired. Please request a new one.",
        )

    user = await get_user_by_id(record.user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid token.")

    hashed = hash_password(body.new_password)
    await update_user(user.id, hashed_password=hashed)
    await mark_reset_token_used(record.id)
    # Revoke all refresh tokens — forces re-login everywhere
    await revoke_all_user_refresh_tokens(user.id)

    return MessageResponse(
        message="Password reset successfully. Please sign in with your new password."
    )


# ── GET CURRENT USER ───────────────────────────────────────────────────────────

@router.get("/me", response_model=UserResponse)
async def get_me(current_user: UserRecord = Depends(get_current_user)) -> UserResponse:
    """Return the authenticated user's profile."""
    return UserResponse.from_record(current_user)


# ── UPDATE PROFILE ─────────────────────────────────────────────────────────────

@router.patch("/me", response_model=UserResponse)
async def update_profile(
    body: UpdateProfileRequest,
    current_user: UserRecord = Depends(get_current_user),
) -> UserResponse:
    """Update user's full name or avatar URL."""
    updates = body.model_dump(exclude_none=True)
    if not updates:
        return UserResponse.from_record(current_user)

    updated = await update_user(current_user.id, **updates)
    return UserResponse.from_record(updated)


# ── CHANGE PASSWORD ────────────────────────────────────────────────────────────

@router.patch("/me/password", response_model=MessageResponse)
async def change_password(
    body: ChangePasswordRequest,
    response: Response,
    current_user: UserRecord = Depends(get_current_user),
) -> MessageResponse:
    """
    Change password (requires current password).
    All other sessions (refresh tokens) are revoked after change.
    """
    if not safe_verify(body.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect.",
        )

    hashed = hash_password(body.new_password)
    await update_user(current_user.id, hashed_password=hashed)

    # Revoke all refresh tokens (including current session)
    await revoke_all_user_refresh_tokens(current_user.id)
    _clear_refresh_cookie(response)

    return MessageResponse(
        message="Password changed. All other sessions have been signed out."
    )
