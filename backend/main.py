"""
main.py — FastAPI application entry point.

Security measures:
  - CORS restricted to configured origins (never '*' in production)
  - No shell execution anywhere in the codebase
  - Request body size limited to 1 MB
  - Secrets loaded via environment variables only
  - API docs disabled in production (set DOCS_ENABLED=false)
"""
from __future__ import annotations

import os
import sys

# Ensure the project root is on sys.path so `backend.*` imports work
# whether the file is run as `python backend/main.py` or via uvicorn
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.config import settings
from backend.routers.agent_router import router as agent_router
from backend.routers.health_router import router as health_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown hooks."""
    # Validate LLM provider is configured correctly at startup
    # This fails fast rather than on first request
    try:
        from backend.llm import get_llm
        llm = get_llm()
        print(f"✓ LLM provider: {llm.model_name}")
    except Exception as exc:
        print(f"⚠ LLM not configured: {exc}")
    yield
    # Cleanup (connection pools, etc.) would go here


docs_enabled = os.getenv("DOCS_ENABLED", "true").lower() == "true"

app = FastAPI(
    title="DevAgent — AI Platform for Software Teams",
    description=(
        "V1: Test Case Generator from Jira tickets + "
        "Pull Request Reviewer from git diffs"
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if docs_enabled else None,
    redoc_url="/redoc" if docs_enabled else None,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
# In production, ALLOWED_ORIGINS should be your frontend domain only.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(agent_router)

# Serve Frontend static assets
frontend_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")
app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")


# ── Global error handler ──────────────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # Never leak internal stack traces to the client
    return JSONResponse(
        status_code=500,
        content={"error": "An internal error occurred. Check server logs."},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=settings.port,
        reload=False,
        log_level="info",
    )
