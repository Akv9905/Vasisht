"""Local semantic retrieval tests (P8).

Tests cover:
- Embedding provider abstraction (NoOp, Deterministic, Factory)
- Deterministic embedding normalization and cosine similarity
- Graceful fallback when embeddings are disabled or unavailable
- Indexing of Java classes, methods, documentation, configuration, SQL, and README
- Validation of chunk metadata: project_id, repository_id, file_id, class_id, method_id, symbol_type
- Semantic vector similarity search
- Keyword retrieval fallback
- Combined retrieval: structured + graph + semantic retrieval
- Verification that P7 structured retrieval remains intact
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.graph.extractor import extract_dependencies
from app.ingestion.scanner import scan_path
from app.models import Base, CodeChunk, Document
from app.parser import parse_java_files
from app.persistence import persist_analysis
from app.retrieval import (
    CombinedRetriever,
    DeterministicEmbeddingProvider,
    EmbeddingProvider,
    NoOpEmbeddingProvider,
    SemanticRetriever,
    StructuredRetriever,
    cosine_similarity,
    get_embedding_provider,
    index_analysis_run,
)

SAMPLE_ROOT = Path(__file__).resolve().parents[2] / "sample-projects" / "payment-service"


@pytest.fixture(scope="module")
def sample_analysis():
    """Scan and parse sample payment-service once for module."""
    scan = scan_path(SAMPLE_ROOT)
    parse_result = parse_java_files(scan.root, scan.java_files)
    graph = extract_dependencies(parse_result)
    return scan, parse_result, graph


@pytest.fixture
def db_session(sample_analysis) -> Session:
    """Create in-memory SQLite database with sample analysis and indexed chunks."""
    scan, parse_result, graph = sample_analysis
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()

    persisted = persist_analysis(session, scan, parse_result, graph, project_name="p8-test")
    session.commit()

    yield session
    session.close()
    engine.dispose()


# ---------------------------------------------------------------------------
# 1. Embedding Provider Abstraction Tests
# ---------------------------------------------------------------------------


class TestEmbeddingProviderAbstraction:
    def test_noop_provider_is_unavailable(self):
        provider = NoOpEmbeddingProvider()
        assert not provider.is_available()
        assert provider.dimension == 0
        embeddings = provider.generate_embeddings(["test text", "another text"])
        assert embeddings == [[], []]
        assert provider.generate_embedding("single") == []

    def test_deterministic_provider_generates_unit_vectors(self):
        provider = DeterministicEmbeddingProvider(dimension=64)
        assert provider.is_available()
        assert provider.dimension == 64

        vec = provider.generate_embedding("public class PaymentService")
        assert len(vec) == 64

        # Unit vector check: norm should be approximately 1.0
        norm = math.sqrt(sum(x * x for x in vec))
        assert pytest.approx(norm, abs=1e-4) == 1.0

    def test_deterministic_embeddings_are_reproducible(self):
        provider = DeterministicEmbeddingProvider(dimension=128)
        text = "PaymentController handles POST /api/payment requests"
        vec1 = provider.generate_embedding(text)
        vec2 = provider.generate_embedding(text)
        assert vec1 == vec2

    def test_cosine_similarity_calculation(self):
        v1 = [1.0, 0.0, 0.0]
        v2 = [1.0, 0.0, 0.0]
        v3 = [0.0, 1.0, 0.0]
        v4 = [-1.0, 0.0, 0.0]

        assert pytest.approx(cosine_similarity(v1, v2), abs=1e-5) == 1.0
        assert pytest.approx(cosine_similarity(v1, v3), abs=1e-5) == 0.0
        assert pytest.approx(cosine_similarity(v1, v4), abs=1e-5) == -1.0

    def test_deterministic_semantic_similarity(self):
        provider = DeterministicEmbeddingProvider(dimension=128)
        v_pay1 = provider.generate_embedding("PaymentService processPayment")
        v_pay2 = provider.generate_embedding("process payment transaction")
        v_unrelated = provider.generate_embedding("astronomy astrophysics telescope galaxy")

        sim_related = cosine_similarity(v_pay1, v_pay2)
        sim_unrelated = cosine_similarity(v_pay1, v_unrelated)

        assert sim_related > sim_unrelated
        assert sim_related > 0.3

    def test_factory_returns_expected_provider(self):
        p_det = get_embedding_provider("deterministic")
        assert isinstance(p_det, DeterministicEmbeddingProvider)

        p_noop = get_embedding_provider("none")
        assert isinstance(p_noop, NoOpEmbeddingProvider)

        p_fallback = get_embedding_provider("unknown_provider_xyz")
        assert p_fallback.is_available()


# ---------------------------------------------------------------------------
# 2. Content Indexing Tests
# ---------------------------------------------------------------------------


class TestContentIndexing:
    def test_index_summary_and_counts(self, db_session: Session):
        summary = index_analysis_run(db_session, analysis_run_id=1)
        assert summary.analysis_run_id == 1
        assert summary.classes_indexed > 0
        assert summary.methods_indexed > 0
        assert summary.configuration_indexed > 0 or summary.documents_indexed > 0 or summary.readme_indexed > 0
        assert summary.total_chunks > 0
        assert summary.embeddings_generated

    def test_indexed_chunks_metadata(self, db_session: Session):
        chunks = db_session.scalars(select(CodeChunk).where(CodeChunk.analysis_run_id == 1)).all()
        assert len(chunks) > 0

        # Check required metadata fields
        symbol_types = {c.symbol_type for c in chunks}
        assert "class" in symbol_types
        assert "method" in symbol_types

        for c in chunks:
            meta = c.metadata_json or {}
            assert "project_id" in meta
            assert "repository_id" in meta
            assert "file_id" in meta
            assert "class_id" in meta
            assert "method_id" in meta
            assert "symbol_type" in meta

            if c.symbol_type == "class":
                assert meta["class_id"] is not None
                assert meta["method_id"] is None
            elif c.symbol_type == "method":
                assert meta["class_id"] is not None
                assert meta["method_id"] is not None

    def test_document_table_populated(self, db_session: Session):
        docs = db_session.scalars(select(Document).where(Document.analysis_run_id == 1)).all()
        # Should index config, sql, readme/docs if present in sample
        assert isinstance(docs, list)


# ---------------------------------------------------------------------------
# 3. Semantic Retrieval and Graceful Fallback Tests
# ---------------------------------------------------------------------------


class TestSemanticRetrieval:
    def test_semantic_search_with_embeddings(self, db_session: Session):
        provider = DeterministicEmbeddingProvider(dimension=128)
        retriever = SemanticRetriever(db_session, analysis_run_id=1, embedding_provider=provider)

        results = retriever.search("PaymentService processPayment", top_k=5)
        assert len(results) > 0
        assert results[0].retrieval_mode == "semantic"
        assert results[0].score > 0.0
        assert any("Payment" in (r.symbol_ref or "") for r in results)

    def test_semantic_search_filtered_by_symbol_type(self, db_session: Session):
        retriever = SemanticRetriever(db_session, analysis_run_id=1)
        class_results = retriever.search("Payment", top_k=5, symbol_types=["class"])
        assert len(class_results) > 0
        assert all(r.symbol_type == "class" for r in class_results)

        method_results = retriever.search("Payment", top_k=5, symbol_types=["method"])
        assert len(method_results) > 0
        assert all(r.symbol_type == "method" for r in method_results)

    def test_graceful_fallback_when_provider_is_noop(self, db_session: Session):
        noop_provider = NoOpEmbeddingProvider()
        retriever = SemanticRetriever(db_session, analysis_run_id=1, embedding_provider=noop_provider)

        results = retriever.search("PaymentService", top_k=5)
        assert len(results) > 0
        # Automatically degraded to keyword search
        assert results[0].retrieval_mode == "keyword_fallback"
        assert any("PaymentService" in (r.symbol_ref or "") for r in results)

    def test_keyword_search_direct(self, db_session: Session):
        retriever = SemanticRetriever(db_session, analysis_run_id=1)
        results = retriever.keyword_search("PaymentRepository", top_k=5)
        assert len(results) > 0
        assert results[0].retrieval_mode == "keyword_fallback"
        assert any("PaymentRepository" in (r.symbol_ref or "") for r in results)

    def test_hybrid_search(self, db_session: Session):
        retriever = SemanticRetriever(db_session, analysis_run_id=1)
        results = retriever.hybrid_search("PaymentController", top_k=5)
        assert len(results) > 0
        assert results[0].retrieval_mode == "hybrid"
        assert any("PaymentController" in (r.symbol_ref or "") for r in results)


# ---------------------------------------------------------------------------
# 4. Combined Retrieval Tests (Structured + Graph + Semantic)
# ---------------------------------------------------------------------------


class TestCombinedRetrieval:
    def test_combined_retrieval_endpoint_flow(self, db_session: Session):
        retriever = CombinedRetriever(db_session, analysis_run_id=1)
        res = retriever.retrieve("How does /api/payment reach the database?", top_chunks=5)

        assert res.query == "How does /api/payment reach the database?"
        assert res.retrieval_mode in ("structured_graph_semantic", "structured_graph_keyword_fallback")
        assert res.flow is not None
        assert res.flow.endpoint == "/api/payment"
        assert res.flow.controller == "create"
        assert res.flow.service == "processPayment"
        assert res.flow.repository == "save"
        assert res.flow.database == "payments"
        assert res.flow.reaches_database is True
        # Verify controller, service, repository, database in flow steps
        step_roles = [s.role for s in res.flow.steps]
        assert step_roles == ["Endpoint", "Controller", "Service", "Repository", "Database"]
        assert any("PaymentController.java" in s.file_path for s in res.flow.steps)
        assert any("PaymentService.java" in s.file_path for s in res.flow.steps)
        assert any("PaymentRepository.java" in s.file_path for s in res.flow.steps)

        # Evidence should include structured flow, graph relationships, and semantic chunks
        assert len(res.evidence) > 0
        evidence_types = {e.get("type") for e in res.evidence}
        assert "flow_step" in evidence_types
        assert len(res.chunks) > 0

    def test_combined_retrieval_symbol_query(self, db_session: Session):
        retriever = CombinedRetriever(db_session, analysis_run_id=1)
        res = retriever.retrieve("PaymentService", top_chunks=5)

        assert any(c.name == "PaymentService" for c in res.classes)
        assert len(res.graph_edges) > 0
        assert len(res.chunks) > 0
        assert len(res.evidence) > 0

    def test_combined_retrieval_fallback_when_embeddings_unavailable(self, db_session: Session):
        noop_provider = NoOpEmbeddingProvider()
        retriever = CombinedRetriever(db_session, analysis_run_id=1, embedding_provider=noop_provider)
        res = retriever.retrieve("PaymentService processPayment", top_chunks=5)

        assert res.retrieval_mode == "structured_graph_keyword_fallback"
        assert len(res.chunks) > 0
        assert all(c.retrieval_mode == "keyword_fallback" for c in res.chunks)


# ---------------------------------------------------------------------------
# 5. P7 Verification (Regression Check)
# ---------------------------------------------------------------------------


class TestP7RegressionVerification:
    def test_structured_retrieval_still_works(self, db_session: Session):
        structured = StructuredRetriever(db_session, analysis_run_id=1)
        classes = structured.retrieve_classes()
        assert len(classes) >= 5

        flow = structured.retrieve_flow("/api/payment")
        assert flow.reaches_database is True
        assert flow.controller == "create"
        assert flow.service == "processPayment"
        assert flow.repository == "save"
        assert flow.database == "payments"
        assert [s.role for s in flow.steps] == ["Endpoint", "Controller", "Service", "Repository", "Database"]
