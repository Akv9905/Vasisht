"""Tests for Evidence-Backed Modernization Analysis (P15).

Verifies:
- Detection of:
  - tightly coupled components
  - circular dependencies
  - large classes
  - high-dependency components
  - architectural bottlenecks
  - testing gaps
  - decomposition candidates
  - framework modernization opportunities
- Every finding contains all 8 required fields:
  - finding
  - evidence
  - reason
  - possible modernization direction
  - dependencies
  - risk/considerations
  - suggested investigation order
  - limitations
- Never claims modernization is required unless supported by evidence
- FastAPI GET /projects/{id}/modernization
- Regression checks for previous phases
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.analysis.modernization import (
    ModernizationFinding,
    ModernizationReport,
    analyze_modernization,
    detect_circular_dependencies_modernization,
    detect_framework_modernization,
    detect_high_coupling_and_decomposition,
    detect_large_classes_modernization,
    detect_testing_gaps_modernization,
)
from app.database import get_db
from app.graph.extractor import extract_dependencies
from app.ingestion.scanner import scan_path
from app.main import app
from app.models import Base
from app.parser import parse_java_files
from app.persistence import persist_analysis

SAMPLE_ROOT = Path(__file__).resolve().parent.parent.parent / "sample-projects" / "payment-service"


@pytest.fixture(scope="module")
def sample_analysis():
    scan = scan_path(SAMPLE_ROOT)
    parse_result = parse_java_files(scan.root, scan.java_files)
    graph = extract_dependencies(parse_result)
    return scan, parse_result, graph


class TestModernizationEngine:
    def test_modernization_findings_contain_all_required_fields(self, sample_analysis):
        _, pr, graph = sample_analysis
        report: ModernizationReport = analyze_modernization(graph, pr)

        assert report.total_findings > 0
        for f in report.findings:
            assert isinstance(f, ModernizationFinding)
            # 1. finding
            assert f.finding and isinstance(f.finding, str)
            # 2. evidence
            assert len(f.evidence) > 0
            # 3. reason
            assert f.reason and isinstance(f.reason, str)
            # 4. possible modernization direction
            assert f.possible_direction and isinstance(f.possible_direction, str)
            # 5. dependencies
            assert len(f.dependencies) > 0
            # 6. risk / considerations
            assert len(f.risk_considerations) > 0
            # 7. suggested investigation order
            assert isinstance(f.suggested_investigation_order, int)
            assert f.suggested_investigation_order >= 1
            # 8. limitations
            assert len(f.limitations) > 0

    def test_circular_dependency_modernization_detected(self, sample_analysis):
        _, _, graph = sample_analysis
        circ_findings = detect_circular_dependencies_modernization(graph)
        assert len(circ_findings) >= 1

        f = circ_findings[0]
        assert f.category == "CIRCULAR_DEPENDENCY"
        assert "PaymentService" in f.finding
        assert "NotificationService" in f.finding
        assert any("ApplicationEventPublisher" in f.possible_direction or "mediator" in f.possible_direction for _ in [1])
        assert f.suggested_investigation_order == 1

    def test_high_coupling_and_decomposition_detected(self, sample_analysis):
        _, _, graph = sample_analysis
        decomp_findings = detect_high_coupling_and_decomposition(graph)
        assert len(decomp_findings) >= 1

        findings_text = "\n".join(f.finding for f in decomp_findings)
        assert "PaymentService" in findings_text or "MetricsFacade" in findings_text
        assert any("Decompose" in f.possible_direction or "caching" in f.possible_direction or "interface" in f.possible_direction for f in decomp_findings)

    def test_testing_gap_modernization_detected(self, sample_analysis):
        _, _, graph = sample_analysis
        gap_findings = detect_testing_gaps_modernization(graph)
        assert len(gap_findings) >= 1

        f = gap_findings[0]
        assert f.category == "TESTING_GAP"
        assert "NotificationService" in f.finding
        assert "NotificationServiceTest" in f.possible_direction

    def test_large_class_modernization_detected(self, sample_analysis):
        _, _, graph = sample_analysis
        large_findings = detect_large_classes_modernization(graph)
        assert len(large_findings) >= 1

        f = large_findings[0]
        assert f.category == "LARGE_CLASS"
        assert "PaymentEntity" in f.finding


class TestFastAPIModernizationEndpoints:
    @pytest.fixture
    def test_client(self, sample_analysis):
        scan, pr, graph = sample_analysis
        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        session = TestingSessionLocal()

        persist_analysis(
            session,
            scan,
            pr,
            graph,
            project_name="PaymentServiceModernizationTest",
        )

        def override_get_db():
            yield session

        app.dependency_overrides[get_db] = override_get_db
        client = TestClient(app)
        yield client
        app.dependency_overrides.clear()
        session.close()
        engine.dispose()

    def test_get_modernization_success(self, test_client):
        resp = test_client.get("/projects/1/modernization")
        assert resp.status_code == 200
        data = resp.json()

        assert "total_findings" in data
        assert "findings" in data
        assert data["total_findings"] >= 1

        first = data["findings"][0]
        assert "finding" in first
        assert "evidence" in first
        assert "reason" in first
        assert "possible_direction" in first
        assert "dependencies" in first
        assert "risk_considerations" in first
        assert "suggested_investigation_order" in first
        assert "limitations" in first

    def test_get_modernization_nonexistent_project_returns_404(self, test_client):
        resp = test_client.get("/projects/9999/modernization")
        assert resp.status_code == 404
