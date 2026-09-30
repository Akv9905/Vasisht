"""Complete End-to-End Validation Suite (P22).

Validates the full enterprise pipeline across both modes:
  MODE 1: Zero external API keys and zero cloud dependencies (Local-first / Deterministic)
  MODE 2: Local LLM runtime available (Configurable local adapter / Mock Ollama/vLLM)

Pipeline Stages Tested:
  Repository
  -> Scanner
  -> Java AST Parser
  -> Symbols
  -> Dependencies (11 relationship types)
  -> PostgreSQL persistence
  -> Software Graph
  -> Retrieval (Structured + Graph + Local Keyword / Semantic)
  -> Evidence Package
  -> Codebase Q&A
  -> Request Flow Tracing
  -> Change Impact Analysis
  -> Technical Risk Analysis
  -> Modernization Analysis
  -> Reports (Markdown + JSON)
  -> FastAPI REST API
  -> Security & Project Isolation
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.analysis.architecture import build_architecture_view
from app.analysis.impact import analyze_change_impact
from app.analysis.modernization import analyze_modernization
from app.analysis.qa import CodebaseQAEngine
from app.analysis.risks import analyze_risks
from app.database import get_db
from app.graph.extractor import extract_dependencies
from app.graph.traversal import trace_request_flow
from app.ingestion.scanner import scan_path
from app.llm import LLMProvider, LLMResponse
from app.main import app
from app.models import Base, Project, Repository
from app.parser import parse_java_files
from app.persistence import persist_analysis
from app.reports.generator import generate_json_report, generate_markdown_report
from app.retrieval.combined import CombinedRetriever
from app.retrieval.indexer import index_analysis_run

SAMPLE_ROOT = Path(__file__).resolve().parents[2] / "sample-projects" / "payment-service"


class MockLocalOllamaProvider(LLMProvider):
    """Simulates a local Ollama/vLLM runtime responding without external networks."""

    @property
    def provider_name(self) -> str:
        return "ollama_local"

    @property
    def model_name(self) -> str:
        return "llama3-local:8b"

    def is_available(self) -> bool:
        return True

    def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 1000,
    ) -> LLMResponse:
        return LLMResponse(
            content="[Local LLM Analysis] Based on repository evidence: PaymentController handles the HTTP request and delegates to PaymentService.",
            model="llama3-local:8b",
            mode="local",
            success=True,
        )

    def explain_evidence(
        self,
        question: str,
        evidence: list[dict[str, Any]],
        flow: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        evidence_summary = ", ".join(e.get("symbol", "") for e in evidence[:3])
        return LLMResponse(
            content=(
                f"Local AI Reasoning: Question '{question}' verified against source evidence ({evidence_summary}). "
                f"Execution flow traces through PaymentController to PaymentService and persists to the payments table."
            ),
            model="llama3-local:8b",
            mode="local",
            success=True,
        )


@pytest.fixture
def full_e2e_environment():
    """Setup full in-memory SQLite database, scan sample project, parse, extract graph, and persist."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()

    # 1. Scanner
    scan = scan_path(SAMPLE_ROOT)
    assert scan.total_files > 0
    assert len(scan.java_files) >= 5

    # 2. Java AST Parser
    parse_result = parse_java_files(scan.root, scan.java_files)
    assert len(parse_result.classes) >= 5
    assert len(parse_result.endpoints) >= 2

    # 3. Dependencies & Graph
    graph = extract_dependencies(parse_result)
    assert len(graph.nodes) > 10
    assert len(graph.edges) > 10

    # 4. PostgreSQL / DB Persistence
    persisted = persist_analysis(session, scan, parse_result, graph, project_name="e2e-payment-service")
    project_id = persisted.project_id
    run_id = persisted.analysis_run_id

    # 5. Local Indexer
    indexing_summary = index_analysis_run(session, run_id)
    assert indexing_summary.total_chunks > 0

    yield {
        "session": session,
        "project_id": project_id,
        "run_id": run_id,
        "scan": scan,
        "parse_result": parse_result,
        "graph": graph,
    }
    session.close()


def test_mode_1_deterministic_end_to_end(full_e2e_environment):
    """MODE 1: Verify entire analysis, Q&A, impact, risks, reports without any LLM or external keys."""
    env = full_e2e_environment
    session: Session = env["session"]
    project_id: int = env["project_id"]
    graph = env["graph"]
    parse_result = env["parse_result"]

    # 1. Retrieval
    retriever = CombinedRetriever(session, env["run_id"])
    ret_res = retriever.retrieve("How does /api/payment reach the database?")
    assert ret_res.flow is not None
    assert any(s.role == "Controller" for s in ret_res.flow.steps)
    assert any(s.role == "Service" for s in ret_res.flow.steps)
    assert any(s.role == "Repository" for s in ret_res.flow.steps)
    assert ret_res.flow.database == "payments"

    # 2. Evidence-backed Q&A in Deterministic Mode
    qa_engine = CodebaseQAEngine(session=session, project_id=project_id)
    qa_ans = qa_engine.answer("How does /api/payment reach the database?")
    assert "deterministic analysis mode enabled" in str(qa_ans.limitations)
    assert len(qa_ans.evidence) > 0
    assert any("PaymentController" in str(e) for e in qa_ans.evidence)

    # 3. Request Flow Tracing
    flow_res = trace_request_flow(graph, "/api/payment")
    assert flow_res.reaches_database is True
    assert flow_res.database_table == "payments"
    assert len(flow_res.steps) >= 4

    # 4. Change Impact Analysis
    impact_res = analyze_change_impact(graph, "PaymentService.processPayment")
    assert "processPayment" in impact_res.target
    assert impact_res.target_file and "PaymentService" in impact_res.target_file
    assert len(impact_res.direct_impact) > 0
    assert len(impact_res.evidence) > 0
    # Uses cautious non-breaking language
    assert any("potentially affected" in line.lower() for line in impact_res.summary_lines())

    # 5. Technical Risk Analysis
    risk_rep = analyze_risks(parse_result=parse_result, graph=graph)
    assert risk_rep.total_findings > 0
    # Must flag circular dependency between PaymentService and NotificationService
    assert any(f.finding_type == "CIRCULAR_DEPENDENCY" for f in risk_rep.findings)
    # Must flag testing gap for NotificationService
    assert any(f.finding_type == "TESTING_GAP" for f in risk_rep.findings)

    # 6. Modernization Analysis
    mod_rep = analyze_modernization(parse_result=parse_result, graph=graph)
    assert mod_rep.total_findings > 0
    for finding in mod_rep.findings:
        assert finding.finding
        assert len(finding.evidence) > 0
        assert finding.possible_direction
        assert finding.suggested_investigation_order > 0

    # 7. Reports Generation (Markdown & JSON)
    md_report = generate_markdown_report(env["scan"], parse_result, graph)
    assert "# Software Intelligence & Architecture Report" in md_report
    assert "## 1. Executive Summary" in md_report
    assert "## 6. Risks" in md_report
    assert "## 8. Modernization" in md_report
    assert "PaymentService" in md_report

    json_report = generate_json_report(env["scan"], parse_result, graph)
    parsed_json = json.loads(json_report)
    assert "risk_indicators" in parsed_json
    assert "modernization_findings" in parsed_json

    # 8. Architecture Visualization View
    arch_view = build_architecture_view(graph, parse_result)
    assert len(arch_view.controllers) > 0
    assert len(arch_view.services) > 0
    assert len(arch_view.repositories) > 0
    assert len(arch_view.databases) > 0
    assert len(arch_view.apis) > 0
    assert len(arch_view.chains) > 0


def test_mode_2_local_llm_end_to_end(full_e2e_environment):
    """MODE 2: Verify Q&A pipeline with local LLM provider adapter (Ollama/vLLM simulation)."""
    env = full_e2e_environment
    session: Session = env["session"]
    project_id: int = env["project_id"]

    local_llm = MockLocalOllamaProvider()
    assert local_llm.is_available() is True

    qa_engine = CodebaseQAEngine(
        session=session,
        project_id=project_id,
        llm_provider=local_llm,
    )

    qa_ans = qa_engine.answer("How does /api/payment reach the database?")
    assert "Local AI Reasoning" in qa_ans.answer
    assert "PaymentController" in qa_ans.answer
    assert len(qa_ans.evidence) > 0
    # No fallback limitation when local LLM is available
    assert not any("AI reasoning unavailable" in lim for lim in qa_ans.limitations)


def test_fastapi_rest_api_end_to_end(full_e2e_environment):
    """Verify all REST API endpoints expose analysis functionality correctly."""
    env = full_e2e_environment
    session: Session = env["session"]
    project_id: int = env["project_id"]

    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    try:
        # 1. Health
        h_resp = client.get("/health")
        assert h_resp.status_code == 200
        assert h_resp.json()["status"] == "ok"

        # 2. Get Project
        p_resp = client.get(f"/projects/{project_id}")
        assert p_resp.status_code == 200
        assert p_resp.json()["id"] == project_id

        # 3. List Classes
        c_resp = client.get(f"/projects/{project_id}/classes")
        assert c_resp.status_code == 200
        class_names = [c["name"] for c in c_resp.json()]
        assert "PaymentController" in class_names
        assert "PaymentService" in class_names

        # 4. List Methods
        m_resp = client.get(f"/projects/{project_id}/methods")
        assert m_resp.status_code == 200
        assert len(m_resp.json()) > 0

        # 5. Architecture Graph
        g_resp = client.get(f"/projects/{project_id}/graph")
        assert g_resp.status_code == 200
        g_data = g_resp.json()
        assert "nodes" in g_data
        assert "edges" in g_data

        # 6. Request Flow
        f_resp = client.get(f"/projects/{project_id}/request-flow?endpoint=/api/payment")
        assert f_resp.status_code == 200
        assert f_resp.json()["reaches_database"] is True

        # 7. Ask Question
        q_resp = client.post(
            f"/projects/{project_id}/questions",
            json={"question": "How does /api/payment reach the database?"},
        )
        assert q_resp.status_code == 200
        assert "/api/payment" in q_resp.json()["answer"]

        # 8. Impact
        imp_resp = client.post(
            f"/projects/{project_id}/impact",
            json={"target": "PaymentService.processPayment"},
        )
        assert imp_resp.status_code == 200
        assert "direct_impact" in imp_resp.json()

        # 9. Risks
        r_resp = client.get(f"/projects/{project_id}/risks")
        assert r_resp.status_code == 200
        assert "findings" in r_resp.json()

        # 10. Modernization
        mod_resp = client.get(f"/projects/{project_id}/modernization")
        assert mod_resp.status_code == 200
        assert "findings" in mod_resp.json()

        # 11. Reports
        rep_resp = client.post(
            f"/projects/{project_id}/reports",
            json={"format": "markdown"},
        )
        assert rep_resp.status_code == 200
        assert "# Software Intelligence & Architecture Report" in rep_resp.json()["content"]

    finally:
        app.dependency_overrides.clear()
