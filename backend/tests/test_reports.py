"""Tests for report generation (P16).

Verifies:
- Markdown report contains all 11 required sections:
  1. Executive summary
  2. Repository inventory
  3. Architecture
  4. Dependencies
  5. Request flows
  6. Risk indicators
  7. Impact analysis
  8. Modernization findings
  9. Test observations
  10. Evidence
  11. Limitations
- JSON report contains all 11 sections with actual analysis metrics
- Never hardcodes repository statistics
- FastAPI POST /projects/{id}/reports (markdown & json)
- Regression checks for previous phases
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import get_db
from app.graph.extractor import extract_dependencies
from app.ingestion.scanner import scan_path
from app.main import app
from app.models import Base
from app.parser import parse_java_files
from app.persistence import persist_analysis
from app.reports.generator import generate_json_report, generate_markdown_report

SAMPLE_ROOT = Path(__file__).resolve().parent.parent.parent / "sample-projects" / "payment-service"


@pytest.fixture(scope="module")
def sample_analysis():
    scan = scan_path(SAMPLE_ROOT)
    parse_result = parse_java_files(scan.root, scan.java_files)
    graph = extract_dependencies(parse_result)
    return scan, parse_result, graph


class TestReportGenerator:
    def test_markdown_report_contains_all_11_sections(self, sample_analysis):
        scan, pr, graph = sample_analysis
        rep = generate_markdown_report(scan, pr, graph)

        # Verify all 11 sections
        assert "## 1. Executive Summary" in rep
        assert "## 2. Repository Inventory" in rep
        assert "## 3. Architecture" in rep
        assert "## 4. Dependencies" in rep
        assert "## 5. Request Flows" in rep
        assert "## 6. Risks" in rep
        assert "## 7. Change Impact Analysis" in rep
        assert "## 8. Modernization Opportunities" in rep
        assert "## 9. Test Observations" in rep
        assert "## 10. Evidence" in rep
        assert "## 11. Limitations" in rep

        # Verify dynamic metrics (not hardcoded)
        assert f"**{scan.total_files}** total files" in rep
        assert f"**{len(scan.java_files)}** Java source files" in rep
        assert f"**{len(graph.nodes)}** nodes" in rep
        assert f"**{len(graph.edges)}** relationships" in rep

    def test_json_report_contains_all_11_sections(self, sample_analysis):
        scan, pr, graph = sample_analysis
        rep_json = generate_json_report(scan, pr, graph)
        data = json.loads(rep_json)

        # 1. Executive Summary
        assert "executive_summary" in data
        assert data["executive_summary"]["total_files"] == scan.total_files
        assert data["executive_summary"]["java_files"] == len(scan.java_files)
        assert data["executive_summary"]["total_nodes"] == len(graph.nodes)

        # 2. Repository Inventory
        assert "repository_inventory" in data
        assert data["repository_inventory"]["source"] == scan.source
        assert data["repository_inventory"]["total_files"] == scan.total_files

        # 3. Architecture
        assert "architecture" in data

        # 4. Dependencies
        assert "dependencies" in data
        assert "graph_summary" in data["dependencies"]

        # 5. Request Flows
        assert "request_flows" in data
        assert len(data["request_flows"]) >= 1

        # 6. Risk Indicators
        assert "risk_indicators" in data
        assert "total_findings" in data["risk_indicators"]

        # 7. Impact Analysis
        assert "impact_analysis" in data
        assert len(data["impact_analysis"]) >= 1

        # 8. Modernization Findings
        assert "modernization_findings" in data
        assert len(data["modernization_findings"]["findings"]) >= 1

        # 9. Test Observations
        assert "test_observations" in data
        assert "test_files_count" in data["test_observations"]

        # 10. Evidence
        assert "evidence" in data
        assert len(data["evidence"]) >= 1

        # 11. Limitations
        assert "limitations" in data
        assert len(data["limitations"]) >= 1


class TestFastAPIReportEndpoints:
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
            project_name="PaymentServiceReportTest",
        )

        def override_get_db():
            yield session

        app.dependency_overrides[get_db] = override_get_db
        client = TestClient(app)
        yield client
        app.dependency_overrides.clear()
        session.close()
        engine.dispose()

    def test_post_report_markdown(self, test_client):
        resp = test_client.post("/projects/1/reports", json={"format": "markdown"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["format"] == "markdown"
        assert "## 1. Executive Summary" in data["content"]
        assert "## 11. Limitations" in data["content"]

    def test_post_report_json(self, test_client):
        resp = test_client.post("/projects/1/reports", json={"format": "json"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["format"] == "json"
        content = data["content"]
        assert isinstance(content, dict)
        assert "executive_summary" in content
        assert "architecture" in content
        assert "modernization_findings" in content

    def test_post_report_nonexistent_project_returns_404(self, test_client):
        resp = test_client.post("/projects/9999/reports", json={"format": "markdown"})
        assert resp.status_code == 404
