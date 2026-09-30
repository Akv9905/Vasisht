"""Local LLM provider adapter (P9).

Supports configurable local runtimes such as Ollama, llama.cpp server,
LocalAI, vLLM, or text-generation-webui.

No hardcoded models.
Configuration comes from environment variables / Settings:
  LLM_PROVIDER=local
  LOCAL_LLM_URL=...
  LOCAL_LLM_MODEL=...
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import get_settings
from app.llm.provider import (
    DETERMINISTIC_FALLBACK_MESSAGE,
    LLMProvider,
    LLMResponse,
)

logger = logging.getLogger(__name__)


class LocalLLMProvider(LLMProvider):
    """Local runtime adapter connecting to Ollama, llama.cpp, or local OpenAI-compatible server."""

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.local_llm_url or "http://localhost:11434").rstrip("/")
        self.model = model or settings.local_llm_model or "llama3"
        self.timeout = timeout or settings.local_llm_timeout or 30.0
        self._client = client

    @property
    def provider_name(self) -> str:
        return "local"

    @property
    def model_name(self) -> str:
        return self.model

    def _get_client(self) -> httpx.Client:
        return self._client or httpx.Client(timeout=self.timeout)

    def is_available(self) -> bool:
        """Check if local LLM service is running and responsive."""
        client = self._get_client()
        try:
            # 1. Try Ollama version endpoint
            resp = client.get(f"{self.base_url}/api/version", timeout=1.0)
            if resp.status_code == 200:
                return True
        except Exception:
            pass

        try:
            # 2. Try OpenAI-compatible /v1/models endpoint
            resp = client.get(f"{self.base_url}/v1/models", timeout=1.0)
            if resp.status_code == 200:
                return True
        except Exception:
            pass

        return False

    def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 1000,
    ) -> LLMResponse:
        """Send prompt to local LLM with automatic graceful fallback."""
        client = self._get_client()

        # Try Ollama native endpoint first: /api/generate
        try:
            payload = {
                "model": self.model,
                "prompt": prompt,
                "system": system_prompt or "",
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_predict": max_tokens,
                },
            }
            resp = client.post(f"{self.base_url}/api/generate", json=payload)
            if resp.status_code == 200:
                data = resp.json()
                content = data.get("response", "").strip()
                tokens = data.get("eval_count")
                return LLMResponse(
                    content=content,
                    model=self.model,
                    mode="local",
                    success=True,
                    tokens_used=tokens,
                )
        except Exception as e:
            logger.debug("Ollama /api/generate failed or not present: %s", e)

        # Try OpenAI-compatible endpoint: /v1/chat/completions
        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            resp = client.post(f"{self.base_url}/v1/chat/completions", json=payload)
            if resp.status_code == 200:
                data = resp.json()
                choices = data.get("choices", [])
                content = choices[0].get("message", {}).get("content", "").strip() if choices else ""
                usage = data.get("usage", {}).get("total_tokens")
                return LLMResponse(
                    content=content,
                    model=self.model,
                    mode="local",
                    success=True,
                    tokens_used=usage,
                )
        except Exception as e:
            logger.warning("Local LLM request failed: %s", e)

        # Automatic fallback: application continues working
        return LLMResponse(
            content=DETERMINISTIC_FALLBACK_MESSAGE,
            model=self.model,
            mode="deterministic_fallback",
            success=False,
            error="Local LLM service unavailable or failed to respond",
        )
