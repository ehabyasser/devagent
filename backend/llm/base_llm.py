"""
llm/base_llm.py

Abstract base for all LLM adapters.
Tradeoff: using an ABC instead of a Protocol keeps method signatures
enforced at import time while still allowing duck typing in tests.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator, Optional


class BaseLLM(ABC):
    """
    Every LLM adapter must implement complete() and stream().
    All adapters receive a list of messages in OpenAI chat-completion format:
        [{"role": "system"|"user"|"assistant", "content": "..."}]
    """

    @abstractmethod
    async def complete(
        self,
        messages: list[dict],
        *,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        response_format: Optional[str] = None,   # "json_object" where supported
    ) -> str:
        """Return the full text response."""
        ...

    @abstractmethod
    async def stream(
        self,
        messages: list[dict],
        *,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        """Yield text chunks as they arrive (for SSE streaming to the UI)."""
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Human-readable model identifier used in output schemas."""
        ...
