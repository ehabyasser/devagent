"""
llm/__init__.py — LLM factory.

Single point of entry: get_llm() returns the configured adapter.
Swap providers by changing LLM_PROVIDER in .env — no code changes.
"""
from __future__ import annotations

from backend.config import settings
from .base_llm import BaseLLM


def get_llm() -> BaseLLM:
    """Factory: returns the configured LLM adapter singleton-like instance."""
    provider = settings.llm_provider

    # Fallback to mock if API key is not configured for openai or anthropic or gemini
    if provider == "openai" and not settings.openai_api_key:
        print("⚠ OPENAI_API_KEY not set. Falling back to MockLLM simulator.")
        provider = "mock"
    elif provider == "anthropic" and not settings.anthropic_api_key:
        print("⚠ ANTHROPIC_API_KEY not set. Falling back to MockLLM simulator.")
        provider = "mock"
    elif provider == "gemini" and not settings.gemini_api_key:
        print("⚠ GEMINI_API_KEY not set. Falling back to MockLLM simulator.")
        provider = "mock"

    if provider == "mock":
        from .mock_llm import MockLLM
        return MockLLM()

    if provider == "openai":
        from .openai_llm import OpenAILLM
        return OpenAILLM()

    if provider == "anthropic":
        from .anthropic_llm import AnthropicLLM
        return AnthropicLLM()

    if provider == "ollama":
        from .ollama_llm import OllamaLLM
        return OllamaLLM()

    if provider == "gemini":
        from .gemini_llm import GeminiLLM
        return GeminiLLM()

    raise ValueError(
        f"Unknown LLM_PROVIDER '{provider}'. "
        "Valid values: openai | anthropic | ollama | mock | gemini"
    )


__all__ = ["get_llm", "BaseLLM"]
