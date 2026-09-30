"""Structured codebase retrieval tests (P7).

Tests cover:
- Retrieval of files, packages, classes, interfaces, methods
- Retrieval of dependencies, callers, callees
- Retrieval of REST API endpoints and database references
- Retrieval of source locations (files and lines)
- Structured architectural flow retrieval:
  "How does /api/payment reach the database?"
  Controller -> Service -> Repository -> Database
- Handling of non-existent symbols and unknown flow queries
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.graph.extractor import extract_dependencies
from app.ingestion.scanner import scan_path
from app.models import Base
from app.parser import parse_java_files
from app.persistence import persist_analysis
from app.retrieval import (
    RetrievedClass,
    RetrievedDatabaseReference,
    RetrievedEndpoint,
    RetrievedFile,
    RetrievedMethod,
    RetrievedPackage,
    StructuredFlowRetrievalResult,
    StructuredRetriever,
)

SAMPLE_ROOT = Path(__file__).resolve().parents[2] / "sample-projects" / "payment-service"


@pytest.fixture(scope="module")
def sample_analysis():
    """Scan and parse sample payment-service once for tests."""
    scan = scan_path(SAMPLE_ROOT)
    parse_result = parse_java_files(scan.root, scan.java_files)
    graph = extract_dependencies(parse_result)
    return scan, parse_result, graph


@pytest.fixture
def db_session(sample_analysis) -> Session:
    """Create in-memory SQLite database populated with sample analysis."""
    scan, parse_result, graph = sample_analysis
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()

    persist_analysis(session, scan, parse_result, graph, project_name="p7-test")
    session.commit()

    yield session
    session.close()
    engine.dispose()


# ---------------------------------------------------------------------------
# File and Package Retrieval Tests
# ---------------------------------------------------------------------------


class TestFileAndPackageRetrieval:
    def test_retrieve_all_files(self, db_session: Session):
        retriever = StructuredRetriever(db_session)
        files = retriever.retrieve_files()
        assert len(files) == 13

    def test_retrieve_java_files_by_category(self, db_session: Session):
        retriever = StructuredRetriever(db_session)
        java_files = retriever.retrieve_files(category="java")
        assert len(java_files) == 9
        assert all("java" in f.categories for f in java_files)

    def test_retrieve_files_by_query(self, db_session: Session):
        retriever = StructuredRetriever(db_session)
        matches = retriever.retrieve_files(query="PaymentController")
        assert len(matches) == 1
        assert "PaymentController.java" in matches[0].relative_path

    def test_retrieve_packages(self, db_session: Session):
        retriever = StructuredRetriever(db_session)
        packages = retriever.retrieve_packages()
        pkg_names = {p.name for p in packages}
        assert "com.example.payment" in pkg_names
        assert "com.example.payment.controller" in pkg_names
        assert "com.example.payment.service" in pkg_names
        assert "com.example.payment.repository" in pkg_names


# ---------------------------------------------------------------------------
# Class and Method Retrieval Tests
# ---------------------------------------------------------------------------


class TestClassAndMethodRetrieval:
    def test_retrieve_classes_by_annotation(self, db_session: Session):
        retriever = StructuredRetriever(db_session)
        controllers = retriever.retrieve_classes(annotation="RestController")
        assert len(controllers) == 2
        names = {c.name for c in controllers}
        assert "PaymentController" in names
        assert "RefundController" in names

    def test_retrieve_service_classes(self, db_session: Session):
        retriever = StructuredRetriever(db_session)
        services = retriever.retrieve_classes(annotation="Service")
        names = {c.name for c in services}
        assert "PaymentService" in names
        assert "NotificationService" in names

    def test_retrieve_classes_by_kind(self, db_session: Session):
        retriever = StructuredRetriever(db_session)
        interfaces = retriever.retrieve_classes(kind="interface")
        assert len(interfaces) == 1
        assert interfaces[0].name == "PaymentRepository"

    def test_retrieve_methods_for_class(self, db_session: Session):
        retriever = StructuredRetriever(db_session)
        methods = retriever.retrieve_methods(class_name="PaymentService")
        m_names = {m.name for m in methods}
        assert "processPayment" in m_names
        assert "acknowledgeNotification" in m_names

    def test_retrieve_methods_by_annotation(self, db_session: Session):
        retriever = StructuredRetriever(db_session)
        transactional_methods = retriever.retrieve_methods(annotation="Transactional")
        assert len(transactional_methods) >= 1
        assert any(m.name == "processPayment" for m in transactional_methods)


# ---------------------------------------------------------------------------
# API and Database References Retrieval Tests
# ---------------------------------------------------------------------------


class TestApiAndDatabaseRetrieval:
    def test_retrieve_endpoint_by_path(self, db_session: Session):
        retriever = StructuredRetriever(db_session)
        endpoints = retriever.retrieve_endpoints(path="/api/payment")
        assert len(endpoints) == 1
        ep = endpoints[0]
        assert ep.http_method == "POST"
        assert ep.path == "/api/payment"
        assert "PaymentController" in ep.handler_class
        assert ep.handler_method == "create"
        assert ep.location.file_path.endswith("PaymentController.java")
        assert ep.location.start_line == 25

    def test_retrieve_database_table_references(self, db_session: Session):
        retriever = StructuredRetriever(db_session)
        db_refs = retriever.retrieve_database_references(kind="table")
        assert len(db_refs) >= 1
        assert any(r.name == "payments" for r in db_refs)
        payments_ref = next(r for r in db_refs if r.name == "payments")
        assert "PaymentEntity" in payments_ref.owning_type

    def test_retrieve_database_column_references(self, db_session: Session):
        retriever = StructuredRetriever(db_session)
        columns = retriever.retrieve_database_references(kind="column")
        col_names = {c.name for c in columns}
        assert "amount" in col_names
        assert "currency" in col_names
        assert "status" in col_names


# ---------------------------------------------------------------------------
# Caller and Callee Retrieval Tests
# ---------------------------------------------------------------------------


class TestCallersAndCalleesRetrieval:
    def test_retrieve_callers_of_paymentservice(self, db_session: Session):
        retriever = StructuredRetriever(db_session)
        callers = retriever.retrieve_callers("PaymentService")
        assert len(callers) > 0
        caller_symbols = {c.caller_symbol for c in callers}
        assert any("PaymentController" in s for s in caller_symbols)

    def test_retrieve_callees_of_paymentcontroller(self, db_session: Session):
        retriever = StructuredRetriever(db_session)
        callees = retriever.retrieve_callees("PaymentController")
        assert len(callees) > 0
        callee_symbols = {c.callee_symbol for c in callees}
        assert any("PaymentService" in s for s in callee_symbols)


# ---------------------------------------------------------------------------
# Source Location Retrieval Tests
# ---------------------------------------------------------------------------


class TestSourceLocationRetrieval:
    def test_retrieve_class_source_location(self, db_session: Session):
        retriever = StructuredRetriever(db_session)
        loc = retriever.retrieve_source_location("PaymentController")
        assert loc is not None
        assert loc.file_path.endswith("PaymentController.java")
        assert loc.start_line == 16

    def test_retrieve_method_source_location(self, db_session: Session):
        retriever = StructuredRetriever(db_session)
        loc = retriever.retrieve_source_location("processPayment")
        assert loc is not None
        assert loc.file_path.endswith("PaymentService.java")
        assert loc.start_line == 29

    def test_retrieve_nonexistent_symbol_location(self, db_session: Session):
        retriever = StructuredRetriever(db_session)
        loc = retriever.retrieve_source_location("NonExistentClass")
        assert loc is None


# ---------------------------------------------------------------------------
# Architectural Flow Retrieval Tests
# ---------------------------------------------------------------------------


class TestArchitecturalFlowRetrieval:
    def test_how_does_api_payment_reach_the_database(self, db_session: Session):
        retriever = StructuredRetriever(db_session)
        flow: StructuredFlowRetrievalResult | None = retriever.retrieve_flow(
            "How does /api/payment reach the database?"
        )
        assert flow is not None
        assert flow.endpoint == "/api/payment"
        assert flow.controller == "create"
        assert flow.service == "processPayment"
        assert flow.repository == "save"
        assert flow.database == "payments"
        assert flow.reaches_database is True

        # Check the 5 sequential steps: Endpoint -> Controller -> Service -> Repository -> Database
        assert len(flow.steps) == 5
        roles = [s.role for s in flow.steps]
        assert roles == ["Endpoint", "Controller", "Service", "Repository", "Database"]

        # Verify concrete source file locations for each step
        assert "PaymentController.java" in flow.steps[0].file_path
        assert "PaymentController.java" in flow.steps[1].file_path
        assert "PaymentService.java" in flow.steps[2].file_path
        assert "PaymentRepository.java" in flow.steps[3].file_path
        assert "PaymentEntity.java" in flow.steps[4].file_path

        # Verify summary lines contain structured architectural chain
        summary = flow.summary_lines()
        assert any("Controller" in l for l in summary)
        assert any("Service" in l for l in summary)
        assert any("Repository" in l for l in summary)
        assert any("Database" in l for l in summary)

    def test_unknown_flow_query(self, db_session: Session):
        retriever = StructuredRetriever(db_session)
        flow = retriever.retrieve_flow("/api/nonexistent")
        assert flow is None
