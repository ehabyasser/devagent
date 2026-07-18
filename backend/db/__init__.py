# backend/db/__init__.py
from backend.db.database import init_db, get_db

__all__ = ["init_db", "get_db"]
