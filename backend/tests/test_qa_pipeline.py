"""Evidence-backed Q&A pipeline tests (P10).

Covers all 7 required test cases:
1. correct question (architectural flow retrieval)
2. insufficient evidence ("Insufficient evidence in the analyzed repository.")
3. LLM unavailable (deterministic fallback mode)
4. semantic retrieval unavailable (graceful fallback)
5. valid evidence (references actual files, classes, methods, source locations)
6. invalid/nonexistent entity
7. project isolation (cross-project data leakage prevention)
+ FastAPI endpoint tests (POST /projects/{project_id}/questions)
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.analysis.qa import CodebaseQAEngine, answer_question
from app.database import get_db
from app.graph.extractor import extract_dependencies
from app.ingestion.scanner import scan_path
from app.llm import (
    DeterministicFallbackLLMProvider,
    LLMProvider,
    LLMResponse,
)
from app.main import app
from app.models import Base, Project, Repository
from app.parser import parse_java_files
from app.persistence import persist_analysis
from app.retrieval import NoOpEmbeddingProvider

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
    """Create in-memory SQLite database populated with Project 1 (payment-service) and Project 2 (empty/isolated)."""
    scan, parse_result, graph = sample_analysis
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()

    # Project 1: payment-service
    persisted1 = persist_analysis(session, scan, parse_result, graph, project_name="payment-service-project")

    # Project 2: isolated project with no runs
    proj2 = Project(name="isolated-other-project")
    session.add(proj2)
    session.commit()

    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def client(db_session: Session) -> TestClient:
    """FastAPI TestClient with overridden get_db dependency."""
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Test Case 1: Correct Question (Request Flow)
# ---------------------------------------------------------------------------


class TestCorrectQuestion:
    def test_how_does_api_payment_reach_the_database(self, db_session: Session):
        engine = CodebaseQAEngine(session=db_session, project_id=1)
        res = engine.answer("How does /api/payment reach the database?")

        assert "Insufficient evidence" not in res.answer
        assert "/api/payment" in res.answer
        assert len(res.flow) == 5

        # Check expected sequence: Endpoint -> Controller -> Service -> Repository -> Database
        roles = [s["role"] for s in res.flow]
        assert roles == ["Endpoint", "Controller", "Service", "Repository", "Database"]

        # Check evidence contains actual classes
        evidence_symbols = {e["symbol"] for e in res.evidence}
        assert any("create" in s or "PaymentController" in s for s in evidence_symbols)
        assert any("processPayment" in s or "PaymentService" in s for s in evidence_symbols)


# ---------------------------------------------------------------------------
# Test Case 2: Insufficient Evidence
# ---------------------------------------------------------------------------


class TestInsufficientEvidence:
    def test_unrelated_question_returns_exact_insufficient_evidence_message(self, db_session: Session):
        engine = CodebaseQAEngine(session=db_session, project_id=1)
        res = engine.answer("What is the recipe for chocolate chip cookies?")

        assert res.answer == "Insufficient evidence in the analyzed repository."
        assert len(res.flow) == 0
        assert len(res.evidence) == 0
        assert len(res.limitations) > 0


# ---------------------------------------------------------------------------
# Test Case 3: LLM Unavailable (Deterministic Fallback Mode)
# ---------------------------------------------------------------------------


class TestLLMUnavailable:
    def test_deterministic_fallback_when_llm_is_disabled(self, db_session: Session):
        fallback_llm = DeterministicFallbackLLMProvider()
        engine = CodebaseQAEngine(
            session=db_session,
            project_id=1,
            llm_provider=fallback_llm,
        )

        res = engine.answer("How does /api/payment reach the database?")
        assert res.answer != "Insufficient evidence in the analyzed repository."
        assert any("AI reasoning unavailable" in lim for lim in res.limitations)
        assert len(res.flow) > 0
        assert len(res.evidence) > 0


# ---------------------------------------------------------------------------
# Test Case 4: Semantic Retrieval Unavailable (Graceful Fallback)
# ---------------------------------------------------------------------------


class TestSemanticRetrievalUnavailable:
    def test_graceful_fallback_to_keyword_and_graph(self, db_session: Session):
        noop_emb = NoOpEmbeddingProvider()
        engine = CodebaseQAEngine(
            session=db_session,
            project_id=1,
            embedding_provider=noop_emb,
        )

        res = engine.answer("How does /api/payment reach the database?")
        assert res.answer != "Insufficient evidence in the analyzed repository."
        assert len(res.flow) == 5
        assert len(res.evidence) > 0


# ---------------------------------------------------------------------------
# Test Case 5: Valid Evidence (Real Files, Classes, Methods, Locations)
# ---------------------------------------------------------------------------


class TestValidEvidence:
    def test_evidence_has_concrete_source_locations(self, db_session: Session):
        engine = CodebaseQAEngine(session=db_session, project_id=1)
        res = engine.answer("How does /api/payment reach the database?")

        assert len(res.evidence) > 0
        for ev in res.evidence:
            assert ev["symbol"]
            assert ev["file_path"]
            assert ev["file_path"] != "unknown"

        # Check line numbers exist on class/method evidence
        has_lines = any(ev["start_line"] is not None for ev in res.evidence)
        assert has_lines


# ---------------------------------------------------------------------------
# Test Case 6: Invalid / Nonexistent Entity
# ---------------------------------------------------------------------------


class TestInvalidNonexistentEntity:
    def test_nonexistent_endpoint_and_class(self, db_session: Session):
        engine = CodebaseQAEngine(session=db_session, project_id=1)
        res = engine.answer("How does /api/nonexistent reach the AlienDatabase?")

        assert res.answer == "Insufficient evidence in the analyzed repository."
        assert len(res.flow) == 0


# ---------------------------------------------------------------------------
# Test Case 7: Project Isolation
# ---------------------------------------------------------------------------


class TestProjectIsolation:
    def test_project_cannot_access_other_project_data(self, db_session: Session):
        # Project 2 is empty; it must NOT return Project 1's payment-service data!
        engine_proj2 = CodebaseQAEngine(session=db_session, project_id=2)
        res = engine_proj2.answer("How does /api/payment reach the database?")

        assert res.answer == "Insufficient evidence in the analyzed repository."
        assert len(res.flow) == 0
        assert len(res.evidence) == 0

    def test_nonexistent_project_id_raises_value_error(self, db_session: Session):
        with pytest.raises(ValueError, match="Project with ID 99999 not found"):
            CodebaseQAEngine(session=db_session, project_id=99999)


# ---------------------------------------------------------------------------
# FastAPI Endpoint Tests (POST /projects/{project_id}/questions)
# ---------------------------------------------------------------------------


class TestFastAPIQuestionsEndpoint:
    def test_api_question_success(self, client: TestClient):
        response = client.post(
            "/projects/1/questions",
            json={"question": "How does /api/payment reach the database?"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "answer" in data
        assert "evidence" in data
        assert "flow" in data
        assert "limitations" in data

        assert len(data["flow"]) == 5
        assert len(data["evidence"]) > 0

    def test_api_question_insufficient_evidence(self, client: TestClient):
        response = client.post(
            "/projects/1/questions",
            json={"question": "Where is the blockchain quantum validator?"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["answer"] == "Insufficient evidence in the analyzed repository."

    def test_api_question_nonexistent_project_returns_404(self, client: TestClient):
        response = client.post(
            "/projects/9999/questions",
            json={"question": "Any question?"},
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()
