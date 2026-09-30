"""Local embedding provider abstraction and implementations (P8).

Provides local, free, zero-cost embedding options:
- Deterministic feature-hashed embeddings (zero external dependencies, runs anywhere on CPU)
- FastEmbed provider (optional local ONNX runtime)
- SentenceTransformer provider (optional local PyTorch runtime)
- Ollama provider (optional local Ollama daemon)
- NoOp provider (graceful fallback when embeddings are disabled or unavailable)

Never requires paid external APIs.
"""

from __future__ import annotations

import hashlib
import logging
import math
import re
from abc import ABC, abstractmethod
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)


def cosine_similarity(v1: list[float] | None, v2: list[float] | None) -> float:
    """Compute cosine similarity between two unit or raw vectors."""
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot = 0.0
    norm1 = 0.0
    norm2 = 0.0
    for a, b in zip(v1, v2):
        dot += a * b
        norm1 += a * a
        norm2 += b * b
    if norm1 <= 1e-12 or norm2 <= 1e-12:
        return 0.0
    return max(-1.0, min(1.0, dot / (math.sqrt(norm1) * math.sqrt(norm2))))


def l2_normalize(vec: list[float]) -> list[float]:
    """Normalize vector to unit length."""
    norm = math.sqrt(sum(x * x for x in vec))
    if norm <= 1e-12:
        return [0.0] * len(vec)
    return [x / norm for x in vec]


class EmbeddingProvider(ABC):
    """Abstract interface for embedding generation."""

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if this provider can generate embeddings right now."""
        ...

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Embedding vector dimension."""
        ...

    @abstractmethod
    def generate_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Generate embedding vectors for a list of texts."""
        ...

    def generate_embedding(self, text: str) -> list[float]:
        """Convenience method for a single text."""
        res = self.generate_embeddings([text])
        return res[0] if res else []


class NoOpEmbeddingProvider(EmbeddingProvider):
    """Placeholder provider used when embeddings are disabled or unavailable.

    Signals is_available() = False so retrievers automatically fall back
    to structured + keyword + graph retrieval.
    """

    def is_available(self) -> bool:
        return False

    @property
    def dimension(self) -> int:
        return 0

    def generate_embeddings(self, texts: list[str]) -> list[list[float]]:
        return [[] for _ in texts]


class DeterministicEmbeddingProvider(EmbeddingProvider):
    """Zero-dependency, CPU-only deterministic embedding provider.

    Projects text tokens and n-grams into a fixed-dimensional unit hypersphere
    using signed hash projections (SimHash / random projection style).
    Produces consistent, cosine-comparable dense representations where
    lexical and semantic token overlaps yield high positive cosine similarity.
    """

    def __init__(self, dimension: int = 128) -> None:
        self._dim = max(16, dimension)

    def is_available(self) -> bool:
        return True

    @property
    def dimension(self) -> int:
        return self._dim

    def _tokenize(self, text: str) -> list[str]:
        raw_words = re.findall(r"[A-Za-z0-9_]+", text)
        tokens: list[str] = []
        for w in raw_words:
            tokens.append(w.lower())
            # Split camelCase: "PaymentService" -> "Payment", "Service"
            sub = re.findall(r"[A-Z]?[a-z0-9]+|[A-Z]+(?=[A-Z][a-z0-9]|\b)", w)
            if len(sub) > 1:
                for s in sub:
                    tokens.append(s.lower())
            # Split snake_case
            parts = [p for p in w.split("_") if p]
            if len(parts) > 1:
                for p in parts:
                    tokens.append(p.lower())
        # Add word bigrams for phrase context
        for i in range(len(tokens) - 1):
            tokens.append(f"{tokens[i]}_{tokens[i+1]}")
        return tokens

    def _hash_token(self, token: str) -> tuple[int, float]:
        """Derive bucket index and signed weight (-1.0 or +1.0) for a token."""
        h = hashlib.md5(token.encode("utf-8")).digest()
        bucket = int.from_bytes(h[:4], "big") % self._dim
        sign = 1.0 if (h[4] & 1) == 1 else -1.0
        return bucket, sign

    def generate_embeddings(self, texts: list[str]) -> list[list[float]]:
        results: list[list[float]] = []
        for text in texts:
            if not text or not text.strip():
                results.append([0.0] * self._dim)
                continue
            tokens = self._tokenize(text)
            vec = [0.0] * self._dim
            for t in tokens:
                bucket, sign = self._hash_token(t)
                vec[bucket] += sign
            norm_vec = l2_normalize(vec)
            results.append(norm_vec)
        return results


class FastEmbedEmbeddingProvider(EmbeddingProvider):
    """Local ONNX-based embedding provider using fastembed if installed."""

    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5") -> None:
        self.model_name = model_name
        self._model: Any = None
        self._dim = 384
        try:
            from fastembed import TextEmbedding

            self._model = TextEmbedding(model_name=self.model_name)
        except Exception as e:
            logger.debug(f"fastembed not available: {e}")
            self._model = None

    def is_available(self) -> bool:
        return self._model is not None

    @property
    def dimension(self) -> int:
        return self._dim

    def generate_embeddings(self, texts: list[str]) -> list[list[float]]:
        if not self.is_available():
            return [[] for _ in texts]
        embeddings = list(self._model.embed(texts))
        return [list(map(float, vec)) for vec in embeddings]


class SentenceTransformerEmbeddingProvider(EmbeddingProvider):
    """Local PyTorch embedding provider using sentence-transformers if installed."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        self.model_name = model_name
        self._model: Any = None
        self._dim = 384
        try:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
        except Exception as e:
            logger.debug(f"sentence-transformers not available: {e}")
            self._model = None

    def is_available(self) -> bool:
        return self._model is not None

    @property
    def dimension(self) -> int:
        return self._dim

    def generate_embeddings(self, texts: list[str]) -> list[list[float]]:
        if not self.is_available():
            return [[] for _ in texts]
        embeddings = self._model.encode(texts, convert_to_numpy=True)
        return [list(map(float, vec)) for vec in embeddings]


class OllamaEmbeddingProvider(EmbeddingProvider):
    """Local embedding provider via Ollama API."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "nomic-embed-text",
        dim: int = 768,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._dim = dim

    def is_available(self) -> bool:
        try:
            import httpx

            r = httpx.get(f"{self.base_url}/api/version", timeout=1.0)
            return r.status_code == 200
        except Exception:
            return False

    @property
    def dimension(self) -> int:
        return self._dim

    def generate_embeddings(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            import httpx

            results: list[list[float]] = []
            for t in texts:
                resp = httpx.post(
                    f"{self.base_url}/api/embeddings",
                    json={"model": self.model, "prompt": t},
                    timeout=10.0,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    vec = data.get("embedding", [])
                    results.append([float(x) for x in vec])
                else:
                    results.append([0.0] * self._dim)
            return results
        except Exception as e:
            logger.warning(f"Ollama embedding request failed: {e}")
            return [[] for _ in texts]


def get_embedding_provider(provider_type: str | None = None) -> EmbeddingProvider:
    """Factory to retrieve the configured embedding provider.

    Defaults to deterministic local embeddings, or falls back safely to
    NoOpEmbeddingProvider if disabled or unavailable.
    """
    settings = get_settings()
    if not settings.embedding_enabled:
        return NoOpEmbeddingProvider()

    provider = (provider_type or settings.embedding_provider or "deterministic").lower()

    if provider in ("none", "noop", "disabled", "false"):
        return NoOpEmbeddingProvider()

    if provider == "deterministic":
        return DeterministicEmbeddingProvider(dimension=settings.embedding_dim)

    if provider == "fastembed":
        p = FastEmbedEmbeddingProvider(model_name=settings.embedding_model)
        if p.is_available():
            return p
        logger.info("FastEmbed requested but unavailable, falling back to NoOp")
        return NoOpEmbeddingProvider()

    if provider in ("sentence_transformers", "sentence-transformers"):
        p = SentenceTransformerEmbeddingProvider(model_name=settings.embedding_model)
        if p.is_available():
            return p
        logger.info("sentence-transformers requested but unavailable, falling back to NoOp")
        return NoOpEmbeddingProvider()

    if provider == "ollama":
        base_url = settings.embedding_base_url or "http://localhost:11434"
        return OllamaEmbeddingProvider(base_url=base_url, model=settings.embedding_model)

    # Default fallback to deterministic local provider
    return DeterministicEmbeddingProvider(dimension=settings.embedding_dim)
