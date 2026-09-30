"""Request flow tracing tests (P11).

Tests cover:
- Tracing execution flow: Endpoint -> Controller -> Service -> Repository -> Database
- Validation of each step: entity, source_file, method where applicable, relationship, evidence
- Marking unresolved calls / steps as unresolved (never guessing)
- Nonexistent endpoint handling
- FastAPI GET /projects/{project_id}/request-flow endpoint
- FastAPI POST /projects/{project_id}/request-flow endpoint
- Regression verification that P10 Q&A still works
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.analysis.qa import CodebaseQAEngine
from app.database import get_db
from app.graph.extractor import extract_dependencies
from app.graph.traversal import RequestFlowResult, trace_request_flow
from app.ingestion.scanner import scan_path
from app.main import app
from app.models import Base
from app.parser import parse_java_files
from app.persistence import persist_analysis

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
    """Create in-memory SQLite database populated with sample analysis."""
    scan, parse_result, graph = sample_analysis
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()

    persist_analysis(session, scan, parse_result, graph, project_name="payment-service-p11")

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
# 1. Direct Graph Request-Flow Tracing Tests
# ---------------------------------------------------------------------------


class TestRequestFlowTracing:
    def test_trace_payment_endpoint_flow(self, sample_analysis):
        _, _, graph = sample_analysis
        flow: RequestFlowResult = trace_request_flow(graph, "/api/payment")

        assert flow.endpoint == "/api/payment"
        assert flow.reaches_database is True
        assert flow.database_table == "payments"
        assert len(flow.steps) == 5

        # Check step sequence: Endpoint -> Controller -> Service -> Repository -> Database
        roles = [s.node_kind for s in flow.steps]
        assert roles == ["endpoint", "method", "method", "method", "database_table"]

        # Step 1: Endpoint
        step1 = flow.steps[0]
        assert "POST /api/payment" in step1.node_name
        assert step1.file_path.endswith("PaymentController.java")

        # Step 2: Controller method
        step2 = flow.steps[1]
        assert step2.node_name == "create"
        assert step2.relationship == "EXPOSES"
        assert step2.file_path.endswith("PaymentController.java")

        # Step 3: Service method
        step3 = flow.steps[2]
        assert step3.node_name == "processPayment"
        assert step3.relationship == "CALLS"
        assert step3.file_path.endswith("PaymentService.java")

        # Step 4: Repository method
        step4 = flow.steps[3]
        assert step4.node_name == "save"
        assert step4.relationship == "CALLS"
        assert step4.file_path.endswith("PaymentRepository.java")

        # Step 5: Database table
        step5 = flow.steps[4]
        assert step5.node_name == "payments"
        assert step5.relationship == "QUERIES"

    def test_trace_refund_endpoint_flow(self, sample_analysis):
        _, _, graph = sample_analysis
        flow = trace_request_flow(graph, "/api/refund/{paymentId}")

        assert flow.reaches_database is True
        assert flow.database_table == "payments"
        assert len(flow.steps) >= 4

    def test_unresolved_calls_are_recorded(self, sample_analysis):
        _, _, graph = sample_analysis
        flow = trace_request_flow(graph, "/api/payment")

        assert len(flow.unresolved_steps) > 0
        # Check standard JDK / Spring framework calls are identified as unresolved
        assert any("String.valueOf" in c or "body.get" in c for c in flow.unresolved_steps)

    def test_nonexistent_endpoint_returns_unresolved(self, sample_analysis):
        _, _, graph = sample_analysis
        flow = trace_request_flow(graph, "/api/nonexistent")

        assert not flow.reaches_database
        assert flow.database_table is None
        assert len(flow.steps) == 0
        assert len(flow.unresolved_steps) > 0


# ---------------------------------------------------------------------------
# 2. FastAPI Request-Flow Endpoints (GET and POST)
# ---------------------------------------------------------------------------


class TestFastAPIRequestFlowEndpoints:
    def test_get_request_flow_success(self, client: TestClient):
        response = client.get("/projects/1/request-flow?endpoint=/api/payment")
        assert response.status_code == 200
        data = response.json()

        assert data["endpoint"] == "/api/payment"
        assert data["reaches_database"] is True
        assert data["database_table"] == "payments"
        assert len(data["steps"]) == 5

        # Check that every step includes required fields: entity, source_file, method, relationship, evidence
        for step in data["steps"]:
            assert step["step"] > 0
            assert step["entity"]
            assert step["role"]
            assert "source_file" in step
            assert "method" in step
            assert "relationship" in step
            assert "evidence" in step
            assert isinstance(step["evidence"], dict)

    def test_post_request_flow_success(self, client: TestClient):
        response = client.post(
            "/projects/1/request-flow",
            json={"endpoint": "/api/payment"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["reaches_database"] is True
        assert len(data["steps"]) == 5

    def test_request_flow_nonexistent_project_returns_404(self, client: TestClient):
        response = client.get("/projects/9999/request-flow?endpoint=/api/payment")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# 3. Regression: Verify P10 Q&A Still Works
# ---------------------------------------------------------------------------


class TestP10QARegression:
    def test_qa_engine_still_answers_flow_question(self, db_session: Session):
        engine = CodebaseQAEngine(session=db_session, project_id=1)
        res = engine.answer("How does /api/payment reach the database?")

        assert "Insufficient evidence" not in res.answer
        assert len(res.flow) == 5
        assert len(res.evidence) > 0
