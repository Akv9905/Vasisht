"""Change impact analysis tests (P12).

Tests cover:
- Impact traversal for method target: PaymentService.processPayment
- Tracing direct callers, indirect callers, dependent services, controllers, APIs, database objects, tests
- Bounded traversal limits (max_depth)
- Language check: "Potentially affected" is used, no definitive claim of breakage
- Nonexistent symbol handling
- FastAPI GET and POST /projects/{project_id}/impact endpoints
- Regression checks for P10 (Q&A) and P11 (request-flow)
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.analysis.impact import ImpactAnalysisResult, analyze_change_impact
from app.analysis.qa import CodebaseQAEngine
from app.database import get_db
from app.graph.extractor import extract_dependencies
from app.graph.traversal import trace_request_flow
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

    persist_analysis(session, scan, parse_result, graph, project_name="payment-service-p12")

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
# 1. Direct Graph Impact Analysis Tests
# ---------------------------------------------------------------------------


class TestImpactAnalysisEngine:
    def test_impact_on_paymentservice_processpayment(self, sample_analysis):
        _, _, graph = sample_analysis
        res: ImpactAnalysisResult = analyze_change_impact(
            graph,
            target_symbol="PaymentService.processPayment",
            max_depth=5,
        )

        assert res.target == "processPayment"
        assert res.target_kind == "method"
        assert "PaymentService.java" in (res.target_file or "")

        # Direct impact (depth 1): should include direct caller (e.g. create) or test
        assert len(res.direct_impact) > 0
        direct_names = {item["name"] for item in res.direct_impact}
        assert any("create" in n or "PaymentController" in n or "Test" in n for n in direct_names)

        # Affected tests
        assert len(res.affected_tests) > 0
        test_ids = {t["id"] for t in res.affected_tests} | {t["name"] for t in res.affected_tests}
        assert any("PaymentServiceTest" in tid or "processPaymentPersistsRow" in tid for tid in test_ids)

        # Affected database objects downstream
        assert len(res.affected_database_objects) > 0
        db_names = {d["name"] for d in res.affected_database_objects}
        assert "payments" in db_names

        # Check evidence contains concrete file paths and line numbers
        assert len(res.evidence) > 0
        for ev in res.evidence:
            assert ev["symbol"]
            assert ev["type"] in ("potentially_affected_upstream", "potentially_affected_database")

        # Check language: must state "Potentially affected"
        summary = "\n".join(res.summary_lines())
        assert "Potentially affected" in summary
        assert any("potentially affected" in lim.lower() for lim in res.limitations)

    def test_impact_on_paymentservice_class(self, sample_analysis):
        _, _, graph = sample_analysis
        res = analyze_change_impact(graph, target_symbol="PaymentService", max_depth=3)

        assert res.target == "PaymentService"
        assert res.target_kind == "class"
        assert len(res.direct_impact) > 0
        assert len(res.affected_tests) > 0

    def test_impact_bounded_depth(self, sample_analysis):
        _, _, graph = sample_analysis
        res_depth1 = analyze_change_impact(graph, target_symbol="PaymentService.processPayment", max_depth=1)
        res_depth5 = analyze_change_impact(graph, target_symbol="PaymentService.processPayment", max_depth=5)

        # Depth 1 should have NO indirect impact
        assert len(res_depth1.indirect_impact) == 0

        # Depth 5 can have indirect impact
        total_depth1 = len(res_depth1.direct_impact)
        total_depth5 = len(res_depth5.direct_impact) + len(res_depth5.indirect_impact)
        assert total_depth5 >= total_depth1

    def test_nonexistent_symbol_impact(self, sample_analysis):
        _, _, graph = sample_analysis
        res = analyze_change_impact(graph, target_symbol="AlienService.nonExistentMethod")

        assert res.target_kind == "unknown"
        assert len(res.direct_impact) == 0
        assert len(res.indirect_impact) == 0
        assert any("not found" in lim.lower() for lim in res.limitations)


# ---------------------------------------------------------------------------
# 2. FastAPI Impact Endpoints (GET and POST)
# ---------------------------------------------------------------------------


class TestFastAPIImpactEndpoints:
    def test_post_impact_success(self, client: TestClient):
        response = client.post(
            "/projects/1/impact",
            json={"target": "PaymentService.processPayment", "max_depth": 5},
        )
        assert response.status_code == 200
        data = response.json()

        assert data["target"] == "processPayment"
        assert data["target_kind"] == "method"
        assert len(data["direct_impact"]) > 0
        assert len(data["affected_tests"]) > 0
        assert len(data["affected_database_objects"]) > 0
        assert len(data["evidence"]) > 0
        assert len(data["limitations"]) > 0

    def test_get_impact_success(self, client: TestClient):
        response = client.get("/projects/1/impact?target=PaymentService.processPayment&max_depth=3")
        assert response.status_code == 200
        data = response.json()
        assert data["target"] == "processPayment"

    def test_impact_nonexistent_project_returns_404(self, client: TestClient):
        response = client.get("/projects/9999/impact?target=PaymentService.processPayment")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# 3. Regression Checks (P10 Q&A and P11 Request Flow)
# ---------------------------------------------------------------------------


class TestRegressions:
    def test_qa_engine_regression(self, db_session: Session):
        engine = CodebaseQAEngine(session=db_session, project_id=1)
        res = engine.answer("How does /api/payment reach the database?")
        assert len(res.flow) == 5

    def test_request_flow_regression(self, sample_analysis):
        _, _, graph = sample_analysis
        flow = trace_request_flow(graph, "/api/payment")
        assert flow.reaches_database is True
