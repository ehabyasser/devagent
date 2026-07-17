"""
llm/anthropic_llm.py

Anthropic adapter (Claude family).
Note: Anthropic uses a messages API that differs from OpenAI in that
system prompts are passed separately; we handle the conversion here.
"""
from __future__ import annotations

from typing import AsyncIterator, Optional

import anthropic as ant

from .base_llm import BaseLLM
from backend.config import settings


def _split_system(messages: list[dict]) -> tuple[str, list[dict]]:
    """Extract the first system message; Anthropic requires it separately."""
    system = ""
    user_messages = []
    for m in messages:
        if m["role"] == "system" and not system:
            system = m["content"]
        else:
            user_messages.append(m)
    return system, user_messages


class AnthropicLLM(BaseLLM):
    def __init__(self) -> None:
        if not settings.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY is not set.")
        self._client = ant.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self._model = settings.anthropic_model

    @property
    def model_name(self) -> str:
        return f"anthropic/{self._model}"

    async def complete(
        self,
        messages: list[dict],
        *,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        response_format: Optional[str] = None,
    ) -> str:
        system, user_msgs = _split_system(messages)
        resp = await self._client.messages.create(
            model=self._model,
            system=system,
            messages=user_msgs,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return resp.content[0].text if resp.content else ""

    async def stream(
        self,
        messages: list[dict],
        *,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        system, user_msgs = _split_system(messages)
        async with self._client.messages.stream(
            model=self._model,
            system=system,
            messages=user_msgs,
            temperature=temperature,
            max_tokens=max_tokens,
        ) as stream:
            async for text in stream.text_stream:
                yield text
