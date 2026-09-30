"""Tests for deterministic technical-risk indicators (P13).

Verifies:
- Measurable evidence: dependency count, fan-in, fan-out, callers, callees
- Class size and method counts
- Cyclomatic complexity
- Circular dependencies
- Inheritance depth
- Database coupling
- Testing gaps
- API exposure
- No arbitrary AI scores
- High dependency explanation (not automatically bad software)
- FastAPI GET /projects/{id}/risks
- Regression checks for previous phases
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.analysis.risks import (
    RiskFinding,
    RiskReport,
    analyze_risks,
    detect_circular_dependencies,
    detect_class_size_and_methods,
    detect_cyclomatic_complexity,
    detect_database_coupling,
    detect_high_coupling,
    detect_inheritance_depth,
    detect_testing_gaps,
)
from app.database import get_db
from app.models import Base
from app.graph.extractor import extract_dependencies
from app.graph.models import DependencyGraph, GraphEdge, GraphNode, RelationshipType
from app.ingestion.scanner import scan_path
from app.main import app
from app.parser import parse_java_files
from app.persistence import persist_analysis

SAMPLE_ROOT = Path(__file__).resolve().parent.parent.parent / "sample-projects" / "payment-service"


@pytest.fixture(scope="module")
def sample_analysis():
    scan = scan_path(SAMPLE_ROOT)
    parse_result = parse_java_files(scan.root, scan.java_files)
    graph = extract_dependencies(parse_result)
    return scan, parse_result, graph


class TestDeterministicRiskIndicators:
    def test_high_dependency_component_contains_all_metrics(self, sample_analysis):
        _, pr, graph = sample_analysis
        report = analyze_risks(pr, graph)

        high_dep = [f for f in report.findings if f.finding_type == "HIGH_DEPENDENCY_COMPONENT"]
        assert len(high_dep) >= 1

        # Check PaymentService or PaymentController
        svc_finding = next((f for f in high_dep if f.subject == "PaymentService"), None)
        assert svc_finding is not None

        # Verify measurable metrics
        assert "incoming_dependencies" in svc_finding.metrics
        assert "outgoing_dependencies" in svc_finding.metrics
        assert "callers" in svc_finding.metrics
        assert "callees" in svc_finding.metrics
        assert "dependency_count" in svc_finding.metrics

        # Verify evidence strings
        evidence_text = "\n".join(svc_finding.evidence)
        assert "incoming dependencies:" in evidence_text
        assert "outgoing dependencies:" in evidence_text
        assert "callers:" in evidence_text
        assert "callees:" in evidence_text

        # Verify explanation: does not automatically claim high dependency is bad software
        assert "does not automatically denote defective software" in svc_finding.summary

    def test_circular_dependency_detection(self, sample_analysis):
        _, pr, graph = sample_analysis
        circ_findings = detect_circular_dependencies(graph)
        assert len(circ_findings) >= 1

        f = circ_findings[0]
        assert f.severity == "HIGH"
        assert "PaymentService" in f.subject
        assert "NotificationService" in f.subject
        assert "cycle_length" in f.metrics
        assert len(f.evidence) >= 2

    def test_database_coupling_detection(self, sample_analysis):
        _, pr, graph = sample_analysis
        db_findings = detect_database_coupling(graph)
        assert len(db_findings) >= 1

        f = db_findings[0]
        assert "database_references" in f.metrics
        assert len(f.evidence) >= 1
        assert "payments" in "\n".join(f.evidence)

    def test_testing_gap_detection(self, sample_analysis):
        _, pr, graph = sample_analysis
        gaps = detect_testing_gaps(graph)
        assert len(gaps) >= 1
        gap_subjects = {g.subject for g in gaps}
        assert "NotificationService" in gap_subjects

        notif_gap = next(g for g in gaps if g.subject == "NotificationService")
        assert notif_gap.metrics["has_tests"] is False
        assert "no test class references" in notif_gap.evidence[1]

    def test_class_size_and_methods_detection(self, sample_analysis):
        _, pr, graph = sample_analysis
        size_findings = detect_class_size_and_methods(graph, pr)
        # Should identify classes with methods/lines
        for f in size_findings:
            assert "method_count" in f.metrics
            assert "line_count" in f.metrics
            assert any("method count:" in ev for ev in f.evidence)
            assert any("class size:" in ev for ev in f.evidence)

    def test_cyclomatic_complexity_detection(self, sample_analysis):
        _, pr, graph = sample_analysis
        complexity_findings = detect_cyclomatic_complexity(graph, pr)
        for f in complexity_findings:
            assert "cyclomatic_complexity" in f.metrics
            assert f.metrics["cyclomatic_complexity"] >= 6
            assert any("cyclomatic complexity:" in ev for ev in f.evidence)

    def test_inheritance_depth_detection(self):
        # Create a graph with deep inheritance
        graph = DependencyGraph()
        n1 = GraphNode(id="type:com.example.Base", kind="class", name="Base")
        n2 = GraphNode(id="type:com.example.Mid", kind="class", name="Mid")
        n3 = GraphNode(id="type:com.example.Leaf", kind="class", name="Leaf")
        graph.add_node(n1)
        graph.add_node(n2)
        graph.add_node(n3)
        graph.add_edge(GraphEdge(source_id=n3.id, target_id=n2.id, relationship=RelationshipType.EXTENDS, resolved=True))
        graph.add_edge(GraphEdge(source_id=n2.id, target_id=n1.id, relationship=RelationshipType.EXTENDS, resolved=True))

        depth_findings = detect_inheritance_depth(graph)
        assert len(depth_findings) >= 1
        leaf_finding = next(f for f in depth_findings if f.subject == "Leaf")
        assert leaf_finding.metrics["inheritance_depth"] >= 2
        assert "Base" in leaf_finding.metrics["hierarchy"]

    def test_no_arbitrary_ai_scores(self, sample_analysis):
        _, pr, graph = sample_analysis
        report = analyze_risks(pr, graph)
        # Every finding must be an instance of RiskFinding with non-empty evidence
        assert report.total_findings > 0
        for f in report.findings:
            assert isinstance(f, RiskFinding)
            assert f.severity in ("HIGH", "MEDIUM", "LOW", "INFO")
            assert len(f.evidence) > 0
            assert isinstance(f.metrics, dict)
            assert len(f.metrics) > 0


class TestFastAPIRisksEndpoint:
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
            project_name="PaymentServiceRisksTest",
        )

        def override_get_db():
            yield session

        app.dependency_overrides[get_db] = override_get_db
        client = TestClient(app)
        yield client
        app.dependency_overrides.clear()
        session.close()
        engine.dispose()

    def test_get_project_risks_success(self, test_client):
        resp = test_client.get("/projects/1/risks")
        assert resp.status_code == 200
        data = resp.json()

        assert "total_findings" in data
        assert "high_count" in data
        assert "medium_count" in data
        assert "findings" in data
        assert data["total_findings"] >= 1

        types = {f["finding_type"] for f in data["findings"]}
        assert "CIRCULAR_DEPENDENCY" in types or "HIGH_DEPENDENCY_COMPONENT" in types

        # Check evidence in each finding
        for f in data["findings"]:
            assert len(f["evidence"]) > 0
            assert f["severity"] in ("HIGH", "MEDIUM", "LOW", "INFO")

    def test_get_project_risks_nonexistent_project_returns_404(self, test_client):
        resp = test_client.get("/projects/9999/risks")
        assert resp.status_code == 404
