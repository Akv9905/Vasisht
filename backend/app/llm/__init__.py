"""LLM module package (P9).

Provides:
- LLMProvider base abstraction
- LocalLLMProvider (default, local-first runtime adapter)
- OptionalAPIProvider (strictly optional remote adapter)
- DeterministicFallbackLLMProvider (deterministic fallback when LLM is unavailable)
- get_llm_provider factory function
- format_evidence_prompt
"""

from __future__ import annotations

import logging

from app.config import get_settings
from app.llm.local import LocalLLMProvider
from app.llm.optional_api import OptionalAPIProvider
from app.llm.provider import (
    DETERMINISTIC_FALLBACK_MESSAGE,
    DeterministicFallbackLLMProvider,
    LLMProvider,
    LLMResponse,
    format_evidence_prompt,
)

logger = logging.getLogger(__name__)


def get_llm_provider(provider_type: str | None = None) -> LLMProvider:
    """Factory to get the configured LLM provider.

    Resolution:
    1. If explicit provider_type is given, use it.
    2. Otherwise, check settings.llm_provider (default: "local").
    3. If settings.llm_enabled is False or provider is "none", return DeterministicFallbackLLMProvider.
    4. Local mode is the default and never requires paid APIs.
    """
    settings = get_settings()
    resolved_type = (provider_type or settings.llm_provider or "local").lower().strip()

    if not settings.llm_enabled and provider_type is None:
        return DeterministicFallbackLLMProvider()

    if resolved_type in ("none", "disabled", "false", "deterministic"):
        return DeterministicFallbackLLMProvider()

    if resolved_type in ("local", "ollama", "llamacpp"):
        return LocalLLMProvider(
            base_url=settings.local_llm_url,
            model=settings.local_llm_model,
            timeout=settings.local_llm_timeout,
        )

    if resolved_type in ("optional_api", "remote", "api"):
        return OptionalAPIProvider(
            base_url=settings.api_llm_url or settings.llm_base_url,
            model=settings.api_llm_model or settings.llm_model,
            api_key=settings.api_llm_key or settings.llm_api_key,
        )

    # Safe fallback to local provider
    return LocalLLMProvider(
        base_url=settings.local_llm_url,
        model=settings.local_llm_model,
    )


__all__ = [
    "DETERMINISTIC_FALLBACK_MESSAGE",
    "DeterministicFallbackLLMProvider",
    "LLMProvider",
    "LLMResponse",
    "LocalLLMProvider",
    "OptionalAPIProvider",
    "format_evidence_prompt",
    "get_llm_provider",
]
