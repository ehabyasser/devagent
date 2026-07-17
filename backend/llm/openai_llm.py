"""
llm/openai_llm.py

OpenAI adapter. Supports GPT-4o and any chat-completion-compatible model.
Uses structured outputs (response_format=json_object) for deterministic JSON.
"""
from __future__ import annotations

import json
from typing import AsyncIterator, Optional

import openai
from openai import AsyncOpenAI

from .base_llm import BaseLLM
from backend.config import settings


class OpenAILLM(BaseLLM):
    def __init__(self) -> None:
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is not set.")
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        self._model = settings.openai_model

    @property
    def model_name(self) -> str:
        return f"openai/{self._model}"

    async def complete(
        self,
        messages: list[dict],
        *,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        response_format: Optional[str] = None,
    ) -> str:
        kwargs: dict = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format == "json_object":
            kwargs["response_format"] = {"type": "json_object"}

        resp = await self._client.chat.completions.create(**kwargs)
        return resp.choices[0].message.content or ""

    async def stream(
        self,
        messages: list[dict],
        *,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        stream = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta
