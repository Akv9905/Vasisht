"""LLM Provider abstraction and interface contracts (P9).

Core principles:
- Local mode is the default.
- Paid APIs (OpenAI, Anthropic, Gemini, Groq, OpenRouter) are NEVER mandatory.
- If no LLM is available, returns: "LLM unavailable — deterministic analysis mode enabled."
- Never send the entire repository to an LLM; only send relevant retrieved evidence.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from typing import Any

DETERMINISTIC_FALLBACK_MESSAGE = "LLM unavailable — deterministic analysis mode enabled."


@dataclass
class LLMResponse:
    """Standardized response from any LLM provider."""

    content: str
    model: str
    mode: str  # "local" | "optional_api" | "deterministic_fallback"
    success: bool = True
    error: str | None = None
    tokens_used: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def format_evidence_prompt(
    question: str,
    evidence: list[dict[str, Any]],
    flow: list[dict[str, Any]] | None = None,
) -> str:
    """Format strictly bounded, retrieved evidence into an explanation prompt.

    Enforces the core rule: Never send the entire repository to an LLM.
    Only bounded, grounded evidence items are provided.
    """
    evidence_lines: list[str] = []
    for idx, ev in enumerate(evidence, start=1):
        ev_type = ev.get("type", "evidence")
        sym = ev.get("symbol", "")
        file_p = ev.get("file_path", "")
        start_l = ev.get("start_line")
        line_str = f":{start_l}" if start_l else ""
        snippet = ev.get("snippet") or ev.get("details") or ""
        evidence_lines.append(f"[{idx}] {ev_type.upper()}: {sym} ({file_p}{line_str})")
        if snippet:
            # Truncate any long snippets to avoid prompt bloat
            evidence_lines.append(f"     Details: {str(snippet)[:250]}")

    flow_lines: list[str] = []
    if flow:
        for f in flow:
            step = f.get("step", "")
            role = f.get("role", "")
            sym = f.get("symbol", "")
            rel = f" --[{f.get('relationship_to_next')}]-->" if f.get("relationship_to_next") else ""
            flow_lines.append(f"  Step {step}: [{role}] {sym}{rel}")

    prompt = (
        f"You are a software architecture reasoning assistant.\n"
        f"Answer the user's question accurately using ONLY the retrieved evidence below.\n"
        f"If the evidence is insufficient to answer the question, state: 'Insufficient evidence in the analyzed repository.'\n"
        f"Do NOT hallucinate, guess, or invent classes, methods, or database relationships.\n\n"
        f"QUESTION:\n{question}\n\n"
    )

    if flow_lines:
        prompt += "VERIFIED ARCHITECTURAL FLOW:\n" + "\n".join(flow_lines) + "\n\n"

    prompt += "RETRIEVED EVIDENCE:\n"
    if evidence_lines:
        prompt += "\n".join(evidence_lines) + "\n"
    else:
        prompt += "No concrete evidence found in repository.\n"

    prompt += (
        "\nProvide a concise, evidence-backed explanation referencing the exact files, "
        "classes, and methods discovered."
    )
    return prompt


class LLMProvider(ABC):
    """Abstract base class for all LLM providers."""

    @abstractmethod
    def is_available(self) -> bool:
        """Check if provider is configured and currently reachable."""
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Name of the provider implementation."""
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Name of the configured model."""
        ...

    @abstractmethod
    def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 1000,
    ) -> LLMResponse:
        """Generate response text for the given prompt."""
        ...

    def explain_evidence(
        self,
        question: str,
        evidence: list[dict[str, Any]],
        flow: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        """Synthesize an answer using ONLY the retrieved evidence."""
        if not self.is_available():
            return LLMResponse(
                content=DETERMINISTIC_FALLBACK_MESSAGE,
                model="deterministic",
                mode="deterministic_fallback",
                success=False,
                error="LLM provider is not available",
            )
        prompt = format_evidence_prompt(question, evidence, flow)
        return self.generate(
            prompt=prompt,
            system_prompt="You are a strict, evidence-grounded software intelligence assistant.",
            temperature=0.0,
        )


class DeterministicFallbackLLMProvider(LLMProvider):
    """Fallback provider used when no LLM is enabled or reachable."""

    def is_available(self) -> bool:
        return False

    @property
    def provider_name(self) -> str:
        return "deterministic_fallback"

    @property
    def model_name(self) -> str:
        return "none"

    def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 1000,
    ) -> LLMResponse:
        return LLMResponse(
            content=DETERMINISTIC_FALLBACK_MESSAGE,
            model="none",
            mode="deterministic_fallback",
            success=False,
            error="No LLM provider configured or available",
        )
