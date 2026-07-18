"""
backend/schemas/auth.py

Pydantic v2 schemas for the authentication API.
Separates API contracts from DB models (UserRecord).
"""
from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, EmailStr, Field, field_validator


# ── Requests ───────────────────────────────────────────────────────────────────

class SignupRequest(BaseModel):
    email: str = Field(..., description="Email address (will be lowercased)")
    password: str = Field(..., min_length=8, description="Minimum 8 characters")
    full_name: str = Field(default="", max_length=100)

    @field_validator("email")
    @classmethod
    def normalise_email(cls, v: str) -> str:
        return v.lower().strip()

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        from backend.auth.password import validate_password_strength
        error = validate_password_strength(v)
        if error:
            raise ValueError(error)
        return v


class LoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def normalise_email(cls, v: str) -> str:
        return v.lower().strip()


class VerifyEmailRequest(BaseModel):
    token: str = Field(..., min_length=64, max_length=64)


class ResendVerificationRequest(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def normalise_email(cls, v: str) -> str:
        return v.lower().strip()


class ForgotPasswordRequest(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def normalise_email(cls, v: str) -> str:
        return v.lower().strip()


class ResetPasswordRequest(BaseModel):
    token: str = Field(..., min_length=64, max_length=64)
    new_password: str = Field(..., min_length=8)

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        from backend.auth.password import validate_password_strength
        error = validate_password_strength(v)
        if error:
            raise ValueError(error)
        return v


class UpdateProfileRequest(BaseModel):
    full_name: Optional[str] = Field(default=None, max_length=100)
    avatar_url: Optional[str] = Field(default=None, max_length=500)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8)

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        from backend.auth.password import validate_password_strength
        error = validate_password_strength(v)
        if error:
            raise ValueError(error)
        return v


# ── Responses ──────────────────────────────────────────────────────────────────

class UserResponse(BaseModel):
    """Public user object — never includes password hash."""
    id: str
    email: str
    full_name: str
    is_active: bool
    email_verified: bool
    avatar_url: Optional[str]
    is_superuser: bool
    created_at: str
    updated_at: str
    last_login_at: Optional[str]

    @classmethod
    def from_record(cls, user) -> "UserResponse":
        """Convert a UserRecord (DB layer) to a public UserResponse."""
        return cls(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            is_active=user.is_active,
            email_verified=user.email_verified,
            avatar_url=user.avatar_url,
            is_superuser=user.is_superuser,
            created_at=user.created_at,
            updated_at=user.updated_at,
            last_login_at=user.last_login_at,
        )


class TokenResponse(BaseModel):
    """Returned on successful login."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int   # seconds
    user: UserResponse


class AccessTokenResponse(BaseModel):
    """Returned on token refresh."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class MessageResponse(BaseModel):
    """Generic success message."""
    message: str
