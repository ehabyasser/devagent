"""routers/health_router.py"""
from fastapi import APIRouter
from datetime import datetime, timezone
from backend.config import settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "llm_provider": settings.llm_provider,
        "version": "1.0.0",
    }
