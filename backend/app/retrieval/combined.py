"""Combined retrieval engine: structured + graph + semantic/keyword (P8).

Combines:
- Structured retrieval (symbols, classes, methods, endpoints, db references, locations)
- Graph retrieval (call graphs, dependencies, architectural flow paths)
- Semantic retrieval (vector similarity across code chunks, docs, configs, SQL)
- Automatic fallback: If semantic embeddings are unavailable, automatically
  falls back to structured + keyword + graph retrieval.
"""

from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.graph.postgres import PostgresKnowledgeGraph
from app.models import AnalysisRun
from app.retrieval.embeddings import EmbeddingProvider, get_embedding_provider
from app.retrieval.semantic import SemanticRetriever, SemanticSearchResult
from app.retrieval.structured import (
    RetrievedClass,
    RetrievedDatabaseReference,
    RetrievedEndpoint,
    RetrievedMethod,
    StructuredFlowRetrievalResult,
    StructuredRetriever,
)

logger = logging.getLogger(__name__)


@dataclass
class CombinedRetrievalResult:
    """Consolidated retrieval result combining structured, graph, and semantic layers."""

    query: str
    retrieval_mode: str  # "structured_graph_semantic" | "structured_graph_keyword_fallback"
    flow: StructuredFlowRetrievalResult | None = None
    classes: list[RetrievedClass] = field(default_factory=list)
    methods: list[RetrievedMethod] = field(default_factory=list)
    endpoints: list[RetrievedEndpoint] = field(default_factory=list)
    database_references: list[RetrievedDatabaseReference] = field(default_factory=list)
    graph_edges: list[dict[str, Any]] = field(default_factory=list)
    chunks: list[SemanticSearchResult] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)

    def summary_lines(self) -> list[str]:
        lines = [
            f"Combined Retrieval for: '{self.query}'",
            f"  Mode: {self.retrieval_mode}",
        ]
        if self.flow:
            lines.append(
                f"  Flow: {self.flow.endpoint} -> {self.flow.controller} -> {self.flow.service} -> {self.flow.repository} -> {self.flow.database or 'None'}"
            )
            lines.append(f"  Reaches Database: {self.flow.reaches_database}")
        lines.append(f"  Structured Classes: {len(self.classes)}")
        lines.append(f"  Structured Methods: {len(self.methods)}")
        lines.append(f"  Graph Edges: {len(self.graph_edges)}")
        lines.append(f"  Chunks Retrieved: {len(self.chunks)}")
        lines.append(f"  Evidence Items: {len(self.evidence)}")
        return lines

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "retrieval_mode": self.retrieval_mode,
            "flow": self.flow.to_dict() if self.flow else None,
            "classes": [c.to_dict() for c in self.classes],
            "methods": [m.to_dict() for m in self.methods],
            "endpoints": [e.to_dict() for e in self.endpoints],
            "database_references": [d.to_dict() for d in self.database_references],
            "graph_edges": self.graph_edges,
            "chunks": [c.to_dict() for c in self.chunks],
            "evidence": self.evidence,
        }


class CombinedRetriever:
    """Unified retrieval engine coordinating structured, graph, and semantic/keyword search."""

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

        self.structured = StructuredRetriever(session, self.analysis_run_id)
        self.graph = PostgresKnowledgeGraph(session, self.analysis_run_id)
        self.semantic = SemanticRetriever(session, self.analysis_run_id, embedding_provider)

    def retrieve(self, query: str, top_chunks: int = 5) -> CombinedRetrievalResult:
        """Run combined retrieval for a user question or search query."""
        flow_result: StructuredFlowRetrievalResult | None = None
        matched_classes: list[RetrievedClass] = []
        matched_methods: list[RetrievedMethod] = []
        matched_endpoints: list[RetrievedEndpoint] = []
        matched_db_refs: list[RetrievedDatabaseReference] = []
        graph_edges: list[dict[str, Any]] = []
        evidence_list: list[dict[str, Any]] = []
        seen_evidence_keys: set[str] = set()

        def add_evidence(item: dict[str, Any]) -> None:
            key = f"{item.get('type')}:{item.get('symbol')}:{item.get('file_path')}:{item.get('start_line')}"
            if key not in seen_evidence_keys:
                seen_evidence_keys.add(key)
                evidence_list.append(item)

        # 1. Check for flow / endpoint queries
        endpoint_match = re.search(r"(/[a-zA-Z0-9_\-\./{}]*)", query)
        is_flow_query = any(k in query.lower() for k in ("reach", "flow", "call", "database", "how does"))

        if endpoint_match or is_flow_query:
            try:
                flow_result = self.structured.retrieve_flow(query)
                if flow_result:
                    for ev in flow_result.evidence:
                        ev_copy = dict(ev)
                        ev_copy["type"] = "flow_step"
                        add_evidence(ev_copy)
            except Exception as e:
                logger.debug(f"Flow retrieval skipped: {e}")

        # 2. Extract potential symbol names (CamelCase words or identifier tokens)
        words = re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", query)
        for w in words:
            if len(w) <= 2 or w.lower() in ("how", "does", "reach", "the", "database", "what", "where", "with"):
                continue
            # Search classes
            cls_matches = self.structured.retrieve_classes(query=w)
            for c in cls_matches:
                if c not in matched_classes:
                    matched_classes.append(c)
                    add_evidence({
                        "type": "class",
                        "symbol": c.qualified_name,
                        "file_path": c.location.file_path if c.location else None,
                        "start_line": c.location.start_line if c.location else None,
                        "end_line": c.location.end_line if c.location else None,
                        "role": c.kind,
                    })

            # Search methods
            method_matches = self.structured.retrieve_methods(query=w)
            for m in method_matches:
                if m not in matched_methods:
                    matched_methods.append(m)
                    add_evidence({
                        "type": "method",
                        "symbol": f"{m.class_name}.{m.name}",
                        "file_path": m.location.file_path if m.location else None,
                        "start_line": m.location.start_line if m.location else None,
                        "end_line": m.location.end_line if m.location else None,
                        "signature": m.signature,
                    })

        # 3. Graph retrieval for discovered symbols
        symbols_to_query = [c.name for c in matched_classes] + [m.name for m in matched_methods]
        if flow_result:
            symbols_to_query.extend([flow_result.controller, flow_result.service, flow_result.repository])

        for sym in set(filter(None, symbols_to_query)):
            nodes = self.graph.find_nodes(name=sym) or self.graph.find_nodes(query=sym)
            for node in nodes:
                try:
                    downstream = self.graph.get_downstream_dependencies(node.id, max_depth=1)
                    for edge in downstream.visited_edges:
                        rel_val = (
                            edge.relationship.value
                            if hasattr(edge.relationship, "value")
                            else str(edge.relationship)
                        )
                        edge_dict = {
                            "source": edge.source_id,
                            "target": edge.target_id,
                            "relationship": rel_val,
                            "resolved": edge.resolved,
                        }
                        if edge_dict not in graph_edges:
                            graph_edges.append(edge_dict)
                            source_node = self.graph.get_node(edge.source_id)
                            edge_file = (
                                source_node.file_path
                                if (source_node and source_node.file_path)
                                else (node.file_path or "dependency_graph")
                            )
                            add_evidence({
                                "type": "graph_relationship",
                                "symbol": f"{edge.source_id} -> {edge.target_id}",
                                "file_path": edge_file,
                                "relationship": rel_val,
                                "resolved": edge.resolved,
                            })
                except Exception as e:
                    logger.debug("Graph traversal error for node %s: %s", node.id, e)

        # 4. Semantic / Keyword retrieval across chunks
        chunks = self.semantic.search(query, top_k=top_chunks)
        retrieval_mode = "structured_graph_keyword_fallback"
        if chunks and any(c.retrieval_mode == "semantic" for c in chunks):
            retrieval_mode = "structured_graph_semantic"

        for chunk in chunks:
            add_evidence({
                "type": f"chunk_{chunk.symbol_type}",
                "symbol": chunk.symbol_ref,
                "file_path": chunk.file_path,
                "start_line": chunk.start_line,
                "end_line": chunk.end_line,
                "score": chunk.score,
                "snippet": chunk.content[:300],
            })

        return CombinedRetrievalResult(
            query=query,
            retrieval_mode=retrieval_mode,
            flow=flow_result,
            classes=matched_classes,
            methods=matched_methods,
            endpoints=matched_endpoints,
            database_references=matched_db_refs,
            graph_edges=graph_edges,
            chunks=chunks,
            evidence=evidence_list,
        )
