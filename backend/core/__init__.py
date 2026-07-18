"""backend/core/limiter.py — Shared rate limiter instance."""
from slowapi import Limiter
from slowapi.util import get_remote_address

# Defined here to avoid circular imports between main.py and routers
limiter = Limiter(key_func=get_remote_address)
