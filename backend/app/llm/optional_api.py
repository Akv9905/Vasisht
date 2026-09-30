"""Optional API LLM provider adapter (P9).

Strictly optional adapter for remote/external endpoints.
Paid APIs are NEVER mandatory. The system remains fully functional
without API keys or external services.
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


class OptionalAPIProvider(LLMProvider):
    """Optional adapter for user-supplied external or self-hosted API endpoints."""

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        timeout: float = 30.0,
        client: httpx.Client | None = None,
    ) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.api_llm_url or settings.llm_base_url or "").rstrip("/")
        self.model = model or settings.api_llm_model or settings.llm_model or "default"
        self.api_key = api_key or settings.api_llm_key or settings.llm_api_key or ""
        self.timeout = timeout
        self._client = client

    @property
    def provider_name(self) -> str:
        return "optional_api"

    @property
    def model_name(self) -> str:
        return self.model

    def _get_client(self) -> httpx.Client:
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return self._client or httpx.Client(headers=headers, timeout=self.timeout)

    def is_available(self) -> bool:
        """Available only if an endpoint URL is configured."""
        if not self.base_url:
            return False
        client = self._get_client()
        try:
            resp = client.get(f"{self.base_url}/v1/models", timeout=2.0)
            return resp.status_code == 200
        except Exception:
            return False

    def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 1000,
    ) -> LLMResponse:
        """Call optional API with graceful fallback if unavailable."""
        if not self.base_url:
            return LLMResponse(
                content=DETERMINISTIC_FALLBACK_MESSAGE,
                model=self.model,
                mode="deterministic_fallback",
                success=False,
                error="Optional API URL is not configured",
            )

        client = self._get_client()
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

        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            resp = client.post(f"{self.base_url}/v1/chat/completions", json=payload, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                choices = data.get("choices", [])
                content = choices[0].get("message", {}).get("content", "").strip() if choices else ""
                usage = data.get("usage", {}).get("total_tokens")
                return LLMResponse(
                    content=content,
                    model=self.model,
                    mode="optional_api",
                    success=True,
                    tokens_used=usage,
                )
        except Exception as e:
            logger.warning("Optional API LLM request failed: %s", e)

        return LLMResponse(
            content=DETERMINISTIC_FALLBACK_MESSAGE,
            model=self.model,
            mode="deterministic_fallback",
            success=False,
            error="Optional API endpoint unreachable or call failed",
        )
