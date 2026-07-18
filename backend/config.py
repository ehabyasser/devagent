"""
config.py — Centralised settings via pydantic-settings.

All secrets come from environment variables; nothing is hard-coded.
"""
from __future__ import annotations

from typing import List, Literal, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Environment ───────────────────────────────────────────────────────────
    environment: Literal["development", "production"] = Field(
        default="development", alias="ENVIRONMENT"
    )
    debug: bool = Field(default=True, alias="DEBUG")

    # ── LLM ──────────────────────────────────────────────────────────────────
    llm_provider: Literal["openai", "anthropic", "ollama", "mock", "gemini"] = "openai"

    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o", alias="OPENAI_MODEL")

    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    anthropic_model: str = Field(
        default="claude-3-5-sonnet-20241022", alias="ANTHROPIC_MODEL"
    )

    ollama_base_url: str = Field(
        default="http://localhost:11434", alias="OLLAMA_BASE_URL"
    )
    ollama_model: str = Field(default="llama3.2", alias="OLLAMA_MODEL")

    # Google Gemini
    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-3.5-flash", alias="GEMINI_MODEL")

    # ── Jira ─────────────────────────────────────────────────────────────────
    jira_base_url: str = Field(default="", alias="JIRA_BASE_URL")
    jira_email: str = Field(default="", alias="JIRA_EMAIL")
    jira_api_token: str = Field(default="", alias="JIRA_API_TOKEN")

    # ── Server ────────────────────────────────────────────────────────────────
    port: int = 8000
    allowed_origins: List[str] = Field(
        default=["http://localhost:8000", "http://127.0.0.1:8000", "null"],
        alias="ALLOWED_ORIGINS",
    )

    # ── Auth / JWT ────────────────────────────────────────────────────────────
    # CRITICAL: Generate with: python -c "import secrets; print(secrets.token_hex(32))"
    # Must be at least 32 characters. Never commit to git.
    jwt_secret_key: str = Field(
        default="CHANGE_ME_GENERATE_WITH_secrets_token_hex_32_IN_PRODUCTION",
        alias="JWT_SECRET",
    )
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    access_token_expire_minutes: int = Field(
        default=15, alias="ACCESS_TOKEN_EXPIRE_MINUTES"
    )
    refresh_token_expire_days: int = Field(
        default=30, alias="REFRESH_TOKEN_EXPIRE_DAYS"
    )

    # ── Cookie security ───────────────────────────────────────────────────────
    # Set to True in production (HTTPS only). False allows HTTP localhost dev.
    cookie_secure: bool = Field(default=False, alias="COOKIE_SECURE")
    cookie_domain: Optional[str] = Field(default=None, alias="COOKIE_DOMAIN")

    # ── Email / SMTP ──────────────────────────────────────────────────────────
    smtp_host: str = Field(default="", alias="SMTP_HOST")
    smtp_port: int = Field(default=587, alias="SMTP_PORT")
    smtp_user: str = Field(default="", alias="SMTP_USER")
    smtp_password: str = Field(default="", alias="SMTP_PASSWORD")
    smtp_from: str = Field(
        default="DevAgent <noreply@devagent.io>", alias="SMTP_FROM"
    )
    # Set False in dev to skip verification step; emails are logged to console instead
    email_verification_enabled: bool = Field(
        default=False, alias="EMAIL_VERIFICATION_ENABLED"
    )

    # ── Application ───────────────────────────────────────────────────────────
    app_base_url: str = Field(
        default="http://localhost:8000", alias="APP_BASE_URL"
    )
    app_name: str = Field(default="DevAgent", alias="APP_NAME")

    # ── Rate limits (requests per minute) ────────────────────────────────────
    rate_limit_login: str = Field(default="10/minute", alias="RATE_LIMIT_LOGIN")
    rate_limit_signup: str = Field(default="5/minute", alias="RATE_LIMIT_SIGNUP")
    rate_limit_forgot: str = Field(default="3/minute", alias="RATE_LIMIT_FORGOT")


settings = Settings()
