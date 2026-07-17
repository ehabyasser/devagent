"""
llm/gemini_llm.py

Google Gemini API adapter using the OpenAI compatibility layer.
No extra SDK dependencies required.
"""
from __future__ import annotations

from typing import AsyncIterator, Optional
from openai import AsyncOpenAI

from .base_llm import BaseLLM
from backend.config import settings


class GeminiLLM(BaseLLM):
    def __init__(self) -> None:
        if not settings.gemini_api_key:
            raise ValueError("GEMINI_API_KEY is not set.")
        # Point to the official Google Gemini OpenAI compatibility endpoint
        self._client = AsyncOpenAI(
            api_key=settings.gemini_api_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/"
        )
        self._model = settings.gemini_model

    @property
    def model_name(self) -> str:
        return f"gemini/{self._model}"

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
            if chunk.choices and len(chunk.choices) > 0:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
