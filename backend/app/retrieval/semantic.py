"""Semantic and keyword retrieval engine with graceful fallback (P8).

Provides:
- Vector similarity search when local embeddings are available
- Automatic graceful fallback to keyword / token retrieval when embeddings are unavailable
- Hybrid search (semantic + keyword)
- Search across Java classes, methods, documentation, configuration, SQL, and README
- Full metadata retention: project_id, repository_id, file_id, class_id, method_id, symbol_type
"""

from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AnalysisRun, CodeChunk, FileRecord
from app.retrieval.embeddings import (
    EmbeddingProvider,
    cosine_similarity,
    get_embedding_provider,
)

logger = logging.getLogger(__name__)


@dataclass
class SemanticSearchResult:
    """Individual chunk search result."""

    chunk_id: int
    symbol_ref: str | None
    symbol_type: str
    content: str
    file_path: str | None
    start_line: int | None
    end_line: int | None
    score: float
    metadata: dict[str, Any]
    retrieval_mode: str  # "semantic" | "keyword_fallback" | "hybrid"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SemanticRetriever:
    """Executes semantic, keyword, or hybrid retrieval across indexed chunks."""

    def __init__(
        self,
        session: Session,
        analysis_run_id: int | None = None,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self.session = session
        if analysis_run_id is not None:
            self.analysis_run_id = analysis_run_id
        else:
            latest_run = self.session.scalar(
                select(AnalysisRun)
                .where(AnalysisRun.status.in_(["completed", "completed_with_errors"]))
                .order_by(AnalysisRun.id.desc())
                .limit(1)
            )
            if latest_run is None:
                raise ValueError("No analysis runs found in database.")
            self.analysis_run_id = latest_run.id

        self.provider = embedding_provider or get_embedding_provider()
        self._file_cache: dict[int, str] = {}

    def _get_file_path(self, file_id: int | None) -> str | None:
        if not file_id:
            return None
        if file_id not in self._file_cache:
            file_rec = self.session.get(FileRecord, file_id)
            self._file_cache[file_id] = file_rec.relative_path if file_rec else None
        return self._file_cache[file_id]

    def _query_chunks(self, symbol_types: list[str] | None = None) -> list[CodeChunk]:
        stmt = select(CodeChunk).where(CodeChunk.analysis_run_id == self.analysis_run_id)
        if symbol_types:
            stmt = stmt.where(CodeChunk.symbol_type.in_(symbol_types))
        return list(self.session.scalars(stmt).all())

    def search(
        self,
        query: str,
        top_k: int = 10,
        symbol_types: list[str] | None = None,
        min_score: float = 0.0,
    ) -> list[SemanticSearchResult]:
        """Perform search with automatic fallback.

        If embedding provider is available and chunks have embeddings, runs
        vector semantic search. Otherwise, gracefully falls back to keyword
        retrieval.
        """
        if not query or not query.strip():
            return []

        chunks = self._query_chunks(symbol_types=symbol_types)
        if not chunks:
            return []

        # Check if embeddings are available and at least one chunk has an embedding vector
        has_embeddings = any(c.embedding_json is not None for c in chunks)
        if self.provider.is_available() and has_embeddings:
            try:
                results = self._semantic_search(query, chunks, top_k=top_k, min_score=min_score)
                if results:
                    return results
            except Exception as e:
                logger.warning(f"Semantic search failed, falling back to keyword search: {e}")

        # Graceful fallback: structured + keyword retrieval
        return self._keyword_search(query, chunks, top_k=top_k)

    def _semantic_search(
        self,
        query: str,
        chunks: list[CodeChunk],
        top_k: int = 10,
        min_score: float = 0.0,
    ) -> list[SemanticSearchResult]:
        q_vec = self.provider.generate_embedding(query)
        if not q_vec:
            return []

        scored: list[tuple[float, CodeChunk]] = []
        for c in chunks:
            emb = c.embedding_json
            if not emb:
                continue
            sim = cosine_similarity(q_vec, emb)
            if sim >= min_score:
                scored.append((sim, c))

        scored.sort(key=lambda x: x[0], reverse=True)
        results: list[SemanticSearchResult] = []
        for score, c in scored[:top_k]:
            meta = dict(c.metadata_json or {})
            file_path = meta.get("file_path") or self._get_file_path(c.file_id)
            results.append(
                SemanticSearchResult(
                    chunk_id=c.id,
                    symbol_ref=c.symbol_ref,
                    symbol_type=c.symbol_type or "unknown",
                    content=c.content,
                    file_path=file_path,
                    start_line=c.start_line,
                    end_line=c.end_line,
                    score=round(score, 4),
                    metadata=meta,
                    retrieval_mode="semantic",
                )
            )
        return results

    def keyword_search(
        self,
        query: str,
        top_k: int = 10,
        symbol_types: list[str] | None = None,
    ) -> list[SemanticSearchResult]:
        """Direct keyword search over indexed chunks."""
        chunks = self._query_chunks(symbol_types=symbol_types)
        return self._keyword_search(query, chunks, top_k=top_k)

    def _keyword_search(
        self,
        query: str,
        chunks: list[CodeChunk],
        top_k: int = 10,
    ) -> list[SemanticSearchResult]:
        clean_q = query.lower().strip()
        tokens = set(re.findall(r"[a-z0-9]+", clean_q))
        if not tokens:
            return []

        scored: list[tuple[float, CodeChunk]] = []
        for c in chunks:
            content_lower = c.content.lower()
            sym_lower = (c.symbol_ref or "").lower()
            score = 0.0

            # Exact phrase bonus
            if clean_q in content_lower:
                score += 3.0
            if clean_q in sym_lower:
                score += 4.0

            # Token overlap scoring
            for t in tokens:
                if t in sym_lower:
                    score += 2.0
                if t in content_lower:
                    score += 1.0

            if score > 0.0:
                # Normalize score between 0.0 and 1.0
                norm_score = min(1.0, score / (len(tokens) * 3.0 + 4.0))
                scored.append((norm_score, c))

        scored.sort(key=lambda x: x[0], reverse=True)
        results: list[SemanticSearchResult] = []
        for score, c in scored[:top_k]:
            meta = dict(c.metadata_json or {})
            file_path = meta.get("file_path") or self._get_file_path(c.file_id)
            results.append(
                SemanticSearchResult(
                    chunk_id=c.id,
                    symbol_ref=c.symbol_ref,
                    symbol_type=c.symbol_type or "unknown",
                    content=c.content,
                    file_path=file_path,
                    start_line=c.start_line,
                    end_line=c.end_line,
                    score=round(score, 4),
                    metadata=meta,
                    retrieval_mode="keyword_fallback",
                )
            )
        return results

    def hybrid_search(
        self,
        query: str,
        top_k: int = 10,
        symbol_types: list[str] | None = None,
        alpha: float = 0.6,
    ) -> list[SemanticSearchResult]:
        """Combine semantic similarity and keyword scores."""
        chunks = self._query_chunks(symbol_types=symbol_types)
        if not chunks:
            return []

        has_embeddings = any(c.embedding_json is not None for c in chunks)
        if not (self.provider.is_available() and has_embeddings):
            return self._keyword_search(query, chunks, top_k=top_k)

        sem_res = {r.chunk_id: r for r in self._semantic_search(query, chunks, top_k=len(chunks))}
        kw_res = {r.chunk_id: r for r in self._keyword_search(query, chunks, top_k=len(chunks))}

        all_ids = set(sem_res.keys()) | set(kw_res.keys())
        scored: list[tuple[float, SemanticSearchResult]] = []

        for cid in all_ids:
            s_score = sem_res[cid].score if cid in sem_res else 0.0
            k_score = kw_res[cid].score if cid in kw_res else 0.0
            comb_score = alpha * s_score + (1.0 - alpha) * k_score
            base = sem_res.get(cid) or kw_res.get(cid)
            if base:
                base.score = round(comb_score, 4)
                base.retrieval_mode = "hybrid"
                scored.append((comb_score, base))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item[1] for item in scored[:top_k]]
