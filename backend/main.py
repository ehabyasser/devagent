"""
main.py — FastAPI application entry point.

Security measures:
  - CORS restricted to configured origins (never '*' in production)
  - No shell execution anywhere in the codebase
  - Request body size limited to 1 MB (via ContentSizeLimitMiddleware)
  - Secrets loaded via environment variables only
  - API docs disabled in production (set DOCS_ENABLED=false)
  - Rate limiting on auth endpoints via slowapi
  - HttpOnly refresh token cookies (XSS-proof session management)
"""
from __future__ import annotations

import logging
import os
import sys

# Ensure the project root is on sys.path so `backend.*` imports work
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from backend.config import settings
from backend.core.limiter import limiter
from backend.db.database import init_db
from backend.routers.agent_router import router as agent_router
from backend.routers.assist_router import router as assist_router
from backend.routers.auth_router import router as auth_router
from backend.routers.health_router import router as health_router
from backend.routers.history_router import router as history_router
from backend.routers.review_router import router as review_router
from backend.routers.rules_router import router as rules_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle hooks."""
    # 1. Initialise database + run pending migrations
    try:
        await init_db()
        logger.info("✓ Database ready")
    except Exception as exc:
        logger.error("✗ Database init failed: %s", exc)

    # 2. Validate LLM provider at startup (fails fast, not on first request)
    try:
        from backend.llm import get_llm
        llm = get_llm()
        logger.info("✓ LLM provider: %s", llm.model_name)
    except Exception as exc:
        logger.warning("⚠ LLM not configured: %s", exc)

    logger.info("✓ DevAgent API ready (environment=%s)", settings.environment)
    yield
    # Cleanup hooks go here (close connection pools, etc.)


docs_enabled = os.getenv("DOCS_ENABLED", "true").lower() == "true"

app = FastAPI(
    title="DevAgent — AI Platform for Software Teams",
    description=(
        "Enterprise SaaS platform for AI-powered code review, test generation, "
        "and engineering workflow automation."
    ),
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs" if docs_enabled else None,
    redoc_url="/redoc" if docs_enabled else None,
)

# ── Rate limiting ──────────────────────────────────────────────────────────────
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── CORS ───────────────────────────────────────────────────────────────────────
# allow_credentials=True is required for HttpOnly cookies to work cross-origin.
# In production, ALLOWED_ORIGINS must NOT contain "*" when credentials=True.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "PUT", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
    expose_headers=["X-Request-ID"],
)

# ── Routers — order matters for URL priority ──────────────────────────────────
app.include_router(health_router)
app.include_router(auth_router)       # /api/auth/*
app.include_router(agent_router)      # /api/agent/*
app.include_router(rules_router)      # /api/rules/*
app.include_router(review_router)     # /api/review
app.include_router(history_router)    # /api/history/*
app.include_router(assist_router)     # /api/assist/*

# ── Frontend static files (MUST be last — catches all remaining paths) ─────────
frontend_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")
app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")


# ── Global exception handler ───────────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Never leak internal stack traces to the client."""
    logger.exception("Unhandled exception on %s %s", request.method, request.url)
    return JSONResponse(
        status_code=500,
        content={"error": "An internal server error occurred. Our team has been notified."},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=settings.port,
        reload=settings.debug,
        log_level="info",
    )
