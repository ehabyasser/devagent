"""
llm/ollama_llm.py

Ollama adapter for local models (llama3, mistral, codellama, etc.).
Uses Ollama's /api/chat endpoint which mirrors OpenAI's chat completions.
No API key needed — just a running Ollama server.
"""
from __future__ import annotations

import json
from typing import AsyncIterator, Optional

import httpx

from .base_llm import BaseLLM
from backend.config import settings


class OllamaLLM(BaseLLM):
    def __init__(self) -> None:
        self._base_url = settings.ollama_base_url.rstrip("/")
        self._model = settings.ollama_model
        self._client = httpx.AsyncClient(base_url=self._base_url, timeout=120.0)

    @property
    def model_name(self) -> str:
        return f"ollama/{self._model}"

    async def complete(
        self,
        messages: list[dict],
        *,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        response_format: Optional[str] = None,
    ) -> str:
        payload: dict = {
            "model": self._model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        if response_format == "json_object":
            payload["format"] = "json"

        resp = await self._client.post("/api/chat", json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data.get("message", {}).get("content", "")

    async def stream(
        self,
        messages: list[dict],
        *,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        payload = {
            "model": self._model,
            "messages": messages,
            "stream": True,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        async with self._client.stream("POST", "/api/chat", json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line:
                    data = json.loads(line)
                    chunk = data.get("message", {}).get("content", "")
                    if chunk:
                        yield chunk
