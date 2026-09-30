"""Tests for P6 analyzer CLI commands and analysis engines.

Tests cover:
- All 12 CLI subcommands:
  - analyze (default scan, milestone checkmarks)
  - inspect
  - list-classes
  - list-methods
  - show-class
  - show-dependencies
  - show-graph
  - trace-request
  - impact
  - risks
  - ask
  - report (Markdown and JSON)
- Dual-syntax invocation:
  - analyze.py <path> <command>
  - analyze.py <command> <path>
- Risk detectors (circular dependencies, coupling, database coupling, testing gaps)
- Evidence-based Q&A (answer generation, flow, evidence, fallback for unknown)
- Report generator (11 sections, markdown, json)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# Add analyzer-cli to sys.path
CLI_DIR = Path(__file__).resolve().parents[2] / "analyzer-cli"
SAMPLE_ROOT = Path(__file__).resolve().parents[2] / "sample-projects" / "payment-service"

import sys
if str(CLI_DIR) not in sys.path:
    sys.path.insert(0, str(CLI_DIR))

import analyze
from app.analysis import analyze_risks, answer_question
from app.graph.extractor import extract_dependencies
from app.ingestion.scanner import scan_path
from app.parser import parse_java_files
from app.reports import generate_json_report, generate_markdown_report


@pytest.fixture(scope="module")
def parsed_data():
    scan = scan_path(SAMPLE_ROOT)
    parse_result = parse_java_files(scan.root, scan.java_files)
    graph = extract_dependencies(parse_result)
    return scan, parse_result, graph


# ---------------------------------------------------------------------------
# CLI Argument Normalization Tests
# ---------------------------------------------------------------------------


class TestCliNormalization:
    def test_default_analyze(self):
        cmd, path, rem = analyze._normalize_cli_args([str(SAMPLE_ROOT)])
        assert cmd == "analyze"
        assert path == str(SAMPLE_ROOT)
        assert rem == []

    def test_path_first_subcommand(self):
        cmd, path, rem = analyze._normalize_cli_args([str(SAMPLE_ROOT), "ask", "test question"])
        assert cmd == "ask"
        assert path == str(SAMPLE_ROOT)
        assert rem == ["test question"]

    def test_command_first_subcommand(self):
        cmd, path, rem = analyze._normalize_cli_args(["ask", str(SAMPLE_ROOT), "test question"])
        assert cmd == "ask"
        assert path == str(SAMPLE_ROOT)
        assert rem == ["test question"]

    def test_impact_subcommand(self):
        cmd, path, rem = analyze._normalize_cli_args([str(SAMPLE_ROOT), "impact", "PaymentService"])
        assert cmd == "impact"
        assert path == str(SAMPLE_ROOT)
        assert rem == ["PaymentService"]


# ---------------------------------------------------------------------------
# CLI Execution Tests
# ---------------------------------------------------------------------------


class TestCliExecution:
    def test_cli_default_analyze(self, capsys):
        code = analyze.main([str(SAMPLE_ROOT)])
        assert code == 0
        captured = capsys.readouterr()
        assert "Repository scanned" in captured.out
        assert "Java files parsed" in captured.out
        assert "Packages discovered" in captured.out
        assert "Classes discovered" in captured.out
        assert "Methods discovered" in captured.out
        assert "Imports extracted" in captured.out
        assert "Dependencies extracted" in captured.out
        assert "Architecture generated" in captured.out
        assert "Risk analysis complete" in captured.out

    def test_cli_inspect(self, capsys):
        code = analyze.main([str(SAMPLE_ROOT), "inspect"])
        assert code == 0
        captured = capsys.readouterr()
        assert "Repository Inspection" in captured.out
        assert "Verified Architectural Chains" in captured.out

    def test_cli_list_classes(self, capsys):
        code = analyze.main([str(SAMPLE_ROOT), "list-classes"])
        assert code == 0
        captured = capsys.readouterr()
        assert "PaymentController" in captured.out
        assert "PaymentService" in captured.out
        assert "PaymentRepository" in captured.out

    def test_cli_list_methods(self, capsys):
        code = analyze.main([str(SAMPLE_ROOT), "list-methods"])
        assert code == 0
        captured = capsys.readouterr()
        assert "processPayment" in captured.out
        assert "create" in captured.out

    def test_cli_show_class(self, capsys):
        code = analyze.main([str(SAMPLE_ROOT), "show-class", "PaymentController"])
        assert code == 0
        captured = capsys.readouterr()
        assert "Class: PaymentController" in captured.out
        assert "PaymentService" in captured.out

    def test_cli_show_dependencies(self, capsys):
        code = analyze.main([str(SAMPLE_ROOT), "show-dependencies", "PaymentService"])
        assert code == 0
        captured = capsys.readouterr()
        assert "PaymentService" in captured.out
        assert "Outgoing dependencies" in captured.out

    def test_cli_show_graph(self, capsys):
        code = analyze.main([str(SAMPLE_ROOT), "show-graph"])
        assert code == 0
        captured = capsys.readouterr()
        assert "Software Knowledge Graph" in captured.out
        assert "Nodes by kind" in captured.out
        assert "Edges by relationship" in captured.out

    def test_cli_trace_request(self, capsys):
        code = analyze.main([str(SAMPLE_ROOT), "trace-request", "/api/payment"])
        assert code == 0
        captured = capsys.readouterr()
        assert "Request Flow for: /api/payment" in captured.out
        assert "payments" in captured.out

    def test_cli_impact(self, capsys):
        code = analyze.main([str(SAMPLE_ROOT), "impact", "PaymentService.processPayment"])
        assert code == 0
        captured = capsys.readouterr()
        assert "Impact Analysis" in captured.out
        assert "Affected Controllers" in captured.out

    def test_cli_risks(self, capsys):
        code = analyze.main([str(SAMPLE_ROOT), "risks"])
        assert code == 0
        captured = capsys.readouterr()
        assert "Risk Analysis Summary" in captured.out
        assert "CIRCULAR_DEPENDENCY" in captured.out

    def test_cli_ask(self, capsys):
        code = analyze.main([str(SAMPLE_ROOT), "ask", "How does /api/payment reach the database?"])
        assert code == 0
        captured = capsys.readouterr()
        assert "Question: How does /api/payment reach the database?" in captured.out
        assert "Execution Flow" in captured.out
        assert "Evidence" in captured.out

    def test_cli_report(self, capsys):
        code = analyze.main([str(SAMPLE_ROOT), "report", "--format", "markdown"])
        assert code == 0
        captured = capsys.readouterr()
        assert "# Software Intelligence & Architecture Report" in captured.out
        assert "## 1. Executive Summary" in captured.out
        assert "## 3. Architecture" in captured.out
        assert "## 6. Risks" in captured.out

    def test_cli_json_mode(self, capsys):
        code = analyze.main([str(SAMPLE_ROOT), "--json"])
        assert code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["total_files"] == 13
        assert "architecture_verified" in data
        assert "risks" in data


# ---------------------------------------------------------------------------
# Risk Engine Unit Tests
# ---------------------------------------------------------------------------


class TestRiskEngine:
    def test_analyze_risks_detects_circular_dependency(self, parsed_data):
        scan, pr, graph = parsed_data
        report = analyze_risks(pr, graph)
        circ = [f for f in report.findings if f.finding_type == "CIRCULAR_DEPENDENCY"]
        assert len(circ) >= 1
        assert "NotificationService" in circ[0].subject
        assert "PaymentService" in circ[0].subject

    def test_analyze_risks_detects_high_coupling(self, parsed_data):
        scan, pr, graph = parsed_data
        report = analyze_risks(pr, graph)
        coupling = [f for f in report.findings if f.finding_type in ("HIGH_COUPLING", "HIGH_FAN_OUT")]
        assert len(coupling) >= 1
        names = {c.subject for c in coupling}
        assert "PaymentService" in names or "PaymentController" in names

    def test_analyze_risks_detects_testing_gap(self, parsed_data):
        scan, pr, graph = parsed_data
        report = analyze_risks(pr, graph)
        gaps = [f for f in report.findings if f.finding_type == "TESTING_GAP"]
        assert len(gaps) >= 1
        assert any(g.subject == "NotificationService" for g in gaps)


# ---------------------------------------------------------------------------
# Q&A Engine Unit Tests
# ---------------------------------------------------------------------------


class TestQAEngine:
    def test_ask_flow_question(self, parsed_data):
        scan, pr, graph = parsed_data
        res = answer_question("How does /api/payment reach the database?", pr, graph)
        assert "PaymentController" in res.answer or "create" in res.answer
        assert "PaymentService" in res.answer or "processPayment" in res.answer
        assert "payments" in res.answer
        assert res.flow is not None
        assert res.flow.reaches_database is True
        assert len(res.evidence) >= 3

    def test_ask_dependency_question(self, parsed_data):
        scan, pr, graph = parsed_data
        res = answer_question("What does PaymentController depend on?", pr, graph)
        assert "PaymentService" in res.answer
        assert len(res.evidence) >= 1

    def test_ask_database_question(self, parsed_data):
        scan, pr, graph = parsed_data
        res = answer_question("What database tables are referenced?", pr, graph)
        assert "payments" in res.answer

    def test_ask_unknown_question_gives_fallback(self, parsed_data):
        scan, pr, graph = parsed_data
        res = answer_question("What is the meaning of life in cloud architecture?", pr, graph)
        assert res.answer == "Insufficient evidence in the analyzed repository."
        assert len(res.limitations) >= 1


# ---------------------------------------------------------------------------
# Report Generator Tests
# ---------------------------------------------------------------------------


class TestReportGenerator:
    def test_markdown_report_contains_all_11_sections(self, parsed_data):
        scan, pr, graph = parsed_data
        md = generate_markdown_report(scan, pr, graph)
        assert "## 1. Executive Summary" in md
        assert "## 2. Repository Inventory" in md
        assert "## 3. Architecture" in md
        assert "## 4. Dependencies" in md
        assert "## 5. Request Flows" in md
        assert "## 6. Risks" in md
        assert "## 7. Change Impact Analysis" in md
        assert "## 8. Modernization Opportunities" in md
        assert "## 9. Test Observations" in md
        assert "## 10. Evidence" in md
        assert "## 11. Limitations" in md

    def test_json_report_structure(self, parsed_data):
        scan, pr, graph = parsed_data
        raw_json = generate_json_report(scan, pr, graph)
        data = json.loads(raw_json)
        assert "inventory" in data
        assert "architecture" in data
        assert "request_flows" in data
        assert "risks" in data
        assert "limitations" in data
