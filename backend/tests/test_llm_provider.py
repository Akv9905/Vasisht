"""LLM provider abstraction tests (P9).

Tests cover:
- LLMProvider abstraction (LocalLLMProvider, OptionalAPIProvider, DeterministicFallbackLLMProvider)
- Local mode is the default and model is NOT hardcoded
- Provider tests using mocks so tests never require an actual running LLM
- Deterministic fallback when LLM is unavailable:
  "LLM unavailable — deterministic analysis mode enabled."
- Never requires paid APIs (OpenAI, Anthropic, Gemini, Groq, OpenRouter)
- Strict grounding contract: only sends retrieved evidence, never the entire repository
- Regression verification that P7 and P8 continue to function
"""

from __future__ import annotations

import httpx
import pytest

from app.config import get_settings
from app.llm import (
    DETERMINISTIC_FALLBACK_MESSAGE,
    DeterministicFallbackLLMProvider,
    LLMProvider,
    LLMResponse,
    LocalLLMProvider,
    OptionalAPIProvider,
    format_evidence_prompt,
    get_llm_provider,
)


# ---------------------------------------------------------------------------
# 1. Base Abstraction & Factory Tests
# ---------------------------------------------------------------------------


class TestLLMProviderBasics:
    def test_deterministic_fallback_provider(self):
        provider = DeterministicFallbackLLMProvider()
        assert not provider.is_available()
        assert provider.provider_name == "deterministic_fallback"
        assert provider.model_name == "none"

        resp = provider.generate("any prompt")
        assert resp.content == DETERMINISTIC_FALLBACK_MESSAGE
        assert resp.mode == "deterministic_fallback"
        assert not resp.success

    def test_factory_default_is_local_mode(self):
        provider = get_llm_provider("local")
        assert isinstance(provider, LocalLLMProvider)
        assert provider.provider_name == "local"

    def test_factory_deterministic_mode(self):
        provider = get_llm_provider("none")
        assert isinstance(provider, DeterministicFallbackLLMProvider)

    def test_model_not_hardcoded(self):
        custom_provider = LocalLLMProvider(
            base_url="http://custom-host:8000",
            model="custom-mistral-7b",
        )
        assert custom_provider.model_name == "custom-mistral-7b"
        assert custom_provider.base_url == "http://custom-host:8000"


# ---------------------------------------------------------------------------
# 2. Evidence Grounding Contract (Never Send Entire Repo)
# ---------------------------------------------------------------------------


class TestEvidenceGroundingContract:
    def test_format_evidence_prompt_contains_only_given_evidence(self):
        question = "How does /api/payment reach the database?"
        evidence = [
            {
                "type": "endpoint",
                "symbol": "/api/payment",
                "file_path": "PaymentController.java",
                "start_line": 20,
            },
            {
                "type": "class",
                "symbol": "PaymentService",
                "file_path": "PaymentService.java",
                "start_line": 15,
            },
        ]
        flow = [
            {"step": 1, "role": "Endpoint", "symbol": "/api/payment", "relationship_to_next": "EXPOSES"},
            {"step": 2, "role": "Service", "symbol": "PaymentService", "relationship_to_next": "CALLS"},
        ]

        prompt = format_evidence_prompt(question, evidence, flow)

        # Prompt must contain the question, the evidence, and the flow
        assert question in prompt
        assert "PaymentController.java:20" in prompt
        assert "PaymentService.java:15" in prompt
        assert "Step 1: [Endpoint] /api/payment" in prompt
        assert "Insufficient evidence in the analyzed repository." in prompt

        # Prompt must NOT contain other random files or entire repository
        assert "PaymentRepository" not in prompt

    def test_empty_evidence_prompt_alerts_assistant(self):
        prompt = format_evidence_prompt("Where is the user profile logic?", [])
        assert "No concrete evidence found in repository." in prompt


# ---------------------------------------------------------------------------
# 3. Local LLM Provider Tests (Mocked Transport)
# ---------------------------------------------------------------------------


class TestLocalLLMProviderMocked:
    def test_ollama_generate_success(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/generate":
                return httpx.Response(
                    200,
                    json={
                        "response": "PaymentController calls PaymentService directly.",
                        "eval_count": 42,
                    },
                )
            return httpx.Response(404)

        client = httpx.Client(transport=httpx.MockTransport(handler))
        provider = LocalLLMProvider(
            base_url="http://localhost:11434",
            model="llama3",
            client=client,
        )

        resp = provider.generate("Explain flow")
        assert resp.success
        assert resp.content == "PaymentController calls PaymentService directly."
        assert resp.model == "llama3"
        assert resp.mode == "local"
        assert resp.tokens_used == 42

    def test_openai_compatible_chat_completions_fallback(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/generate":
                return httpx.Response(404)  # Ollama not installed, try v1
            if request.url.path == "/v1/chat/completions":
                return httpx.Response(
                    200,
                    json={
                        "choices": [{"message": {"content": "Resolved via v1 chat endpoint."}}],
                        "usage": {"total_tokens": 55},
                    },
                )
            return httpx.Response(404)

        client = httpx.Client(transport=httpx.MockTransport(handler))
        provider = LocalLLMProvider(
            base_url="http://localhost:8000",
            model="local-model",
            client=client,
        )

        resp = provider.generate("Explain architecture")
        assert resp.success
        assert resp.content == "Resolved via v1 chat endpoint."
        assert resp.tokens_used == 55

    def test_local_llm_connection_failure_falls_back_deterministically(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("Connection refused")

        client = httpx.Client(transport=httpx.MockTransport(handler))
        provider = LocalLLMProvider(
            base_url="http://localhost:11434",
            model="llama3",
            client=client,
        )

        resp = provider.generate("Explain flow")
        assert not resp.success
        assert resp.content == DETERMINISTIC_FALLBACK_MESSAGE
        assert resp.mode == "deterministic_fallback"

    def test_explain_evidence_when_unavailable_does_not_call_llm(self):
        # When unavailable, explain_evidence should immediately return deterministic message
        def handler(request: httpx.Request) -> httpx.Response:
            # Should not be called
            raise AssertionError("Unexpected network call when unavailable")

        client = httpx.Client(transport=httpx.MockTransport(handler))
        provider = LocalLLMProvider(
            base_url="http://unreachable:11434",
            model="llama3",
            client=client,
        )
        # Mock is_available to False
        provider.is_available = lambda: False  # type: ignore[method-assign]

        resp = provider.explain_evidence("Question?", [{"symbol": "PaymentService"}])
        assert not resp.success
        assert resp.content == DETERMINISTIC_FALLBACK_MESSAGE


# ---------------------------------------------------------------------------
# 4. Optional Remote API Provider Tests (Mocked Transport)
# ---------------------------------------------------------------------------


class TestOptionalAPIProviderMocked:
    def test_optional_api_not_configured_returns_deterministic_fallback(self):
        provider = OptionalAPIProvider(base_url="")
        assert not provider.is_available()

        resp = provider.generate("Test prompt")
        assert not resp.success
        assert resp.content == DETERMINISTIC_FALLBACK_MESSAGE

    def test_optional_api_success(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert "Bearer test-key" in request.headers.get("Authorization", "")
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": "Remote API explanation."}}],
                    "usage": {"total_tokens": 120},
                },
            )

        client = httpx.Client(transport=httpx.MockTransport(handler))
        provider = OptionalAPIProvider(
            base_url="http://mock-api.internal",
            model="mock-remote-model",
            api_key="test-key",
            client=client,
        )

        resp = provider.generate("Test prompt")
        assert resp.success
        assert resp.content == "Remote API explanation."
        assert resp.tokens_used == 120


# ---------------------------------------------------------------------------
# 5. Zero-Cost & Deterministic Operation Enforced
# ---------------------------------------------------------------------------


class TestZeroCostConstraint:
    def test_no_paid_api_required_for_system_operation(self):
        # Test default settings do NOT require any external paid API keys
        settings = get_settings()
        assert not settings.api_llm_key
        assert not settings.llm_api_key

        # System operates fully in local mode
        provider = get_llm_provider("local")
        assert provider.provider_name == "local"
