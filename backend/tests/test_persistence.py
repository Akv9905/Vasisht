"""P4 persistence tests use SQLite to avoid requiring a PostgreSQL service."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session

from app.graph.extractor import extract_dependencies
from app.ingestion.scanner import scan_path
from app.models import (
    AnalysisRun,
    ApiEndpoint,
    ClassSymbol,
    DatabaseReference,
    Dependency,
    FileRecord,
    GraphEdge,
    GraphNode,
    ImportRecord,
    Method,
    Package,
    Project,
    Repository,
    Base,
)
from app.parser import parse_java_files
from app.persistence import persist_analysis


ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "sample-projects" / "payment-service"


def _sqlite_engine():
    engine = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    return engine


def test_p4_schema_has_planned_tables():
    expected = {
        "projects", "repositories", "files", "packages", "classes", "methods", "fields",
        "imports", "dependencies", "graph_nodes", "graph_edges", "api_endpoints",
        "database_references", "analysis_runs", "documents", "code_chunks", "questions",
        "answers", "evidence", "impact_analyses", "risk_findings", "modernization_findings",
        "users", "audit_logs",
    }
    assert expected <= set(Base.metadata.tables)


def test_persist_sample_analysis_snapshot_and_history():
    scan = scan_path(SAMPLE)
    parsed = parse_java_files(scan.root, scan.java_files)
    graph = extract_dependencies(parsed)
    engine = _sqlite_engine()

    with Session(engine) as session, session.begin():
        first = persist_analysis(session, scan, parsed, graph, project_name="Payment Service")
    with Session(engine) as session, session.begin():
        second = persist_analysis(session, scan, parsed, graph, project_name="Payment Service")

    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Project)) == 1
        assert session.scalar(select(func.count()).select_from(Repository)) == 1
        runs = list(session.scalars(select(AnalysisRun).order_by(AnalysisRun.id)))
        assert [run.id for run in runs] == [first.analysis_run_id, second.analysis_run_id]
        assert all(run.repository_id == first.repository_id for run in runs)
        assert runs[0].status == "completed"
        assert runs[0].file_count == scan.total_files
        assert runs[0].parsed_file_count == parsed.files_parsed
        assert runs[0].graph_node_count == len(graph.nodes)
        assert runs[0].graph_edge_count == len(graph.edges)

        run_id = first.analysis_run_id
        assert session.scalar(select(func.count()).select_from(FileRecord).where(FileRecord.analysis_run_id == run_id)) == scan.total_files
        assert session.scalar(select(func.count()).select_from(Package).where(Package.analysis_run_id == run_id)) == len(parsed.packages)
        assert session.scalar(select(func.count()).select_from(ClassSymbol).where(ClassSymbol.analysis_run_id == run_id)) == len(parsed.classes + parsed.interfaces + parsed.enums)
        assert session.scalar(select(func.count()).select_from(Method).where(Method.analysis_run_id == run_id)) == len(parsed.methods + parsed.constructors)
        assert session.scalar(select(func.count()).select_from(ImportRecord).where(ImportRecord.analysis_run_id == run_id)) == len(parsed.imports)
        assert session.scalar(select(func.count()).select_from(GraphNode).where(GraphNode.analysis_run_id == run_id)) == len(graph.nodes)
        assert session.scalar(select(func.count()).select_from(GraphEdge).where(GraphEdge.analysis_run_id == run_id)) == len(graph.edges)
        assert session.scalar(select(func.count()).select_from(Dependency).where(Dependency.analysis_run_id == run_id)) == sum(
            edge.relationship.value == "DEPENDS_ON" for edge in graph.edges
        )

        endpoints = list(session.scalars(select(ApiEndpoint).where(ApiEndpoint.analysis_run_id == run_id)))
        assert {(ep.http_method, ep.path) for ep in endpoints} >= {
            ("POST", "/api/payment"),
            ("POST", "/api/refund/{paymentId}"),
        }
        references = list(session.scalars(select(DatabaseReference).where(DatabaseReference.analysis_run_id == run_id)))
        assert any(ref.kind == "table" and ref.name == "payments" for ref in references)

    engine.dispose()
