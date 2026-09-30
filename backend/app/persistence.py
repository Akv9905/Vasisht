"""Persist scanner, parser, and dependency-graph output as one analysis run."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from app.graph.models import DependencyGraph as ExtractedGraph
from app.ingestion.scanner import ScanResult
from app.models import (
    AnalysisRun,
    ApiEndpoint,
    ClassSymbol,
    DatabaseReference as DatabaseReferenceRow,
    Dependency,
    Field as FieldRow,
    FileRecord as FileRecordRow,
    GraphEdge as GraphEdgeRow,
    GraphNode as GraphNodeRow,
    ImportRecord,
    Method as MethodRow,
    Package,
    Project,
    Repository,
)
from app.parser.models import ParseResult, SourceRef, TypeInfo


@dataclass(frozen=True)
class PersistedAnalysis:
    project_id: int
    repository_id: int
    analysis_run_id: int


def _source_lines(source: SourceRef | None) -> tuple[int | None, int | None]:
    return (source.start_line, source.end_line) if source else (None, None)


def _path_key(path: str | None) -> str | None:
    return path.replace("\\", "/") if path else None


def _iter_symbols(parse_result: ParseResult) -> list[TypeInfo]:
    # The aggregated lists include nested types and keep their source metadata.
    return parse_result.classes + parse_result.interfaces + parse_result.enums


def persist_analysis(
    session: Session,
    scan: ScanResult,
    parse_result: ParseResult | None,
    graph: ExtractedGraph | None,
    *,
    project_name: str | None = None,
) -> PersistedAnalysis:
    """Store one immutable analysis snapshot within the caller's transaction.

    Repository identity is project + source path. Repeated analyses reuse the
    project/repository rows and create a new run with its own file/symbol/graph
    snapshot so historical runs remain queryable.
    """
    source_path = Path(scan.source)
    default_name = source_path.stem if scan.from_zip else source_path.name
    resolved_project_name = (project_name or default_name or "Repository analysis")[:200]

    project = session.scalar(select(Project).where(Project.name == resolved_project_name))
    if project is None:
        project = Project(name=resolved_project_name)
        session.add(project)
        session.flush()

    repository = session.scalar(
        select(Repository).where(
            Repository.project_id == project.id,
            Repository.source == scan.source,
        )
    )
    if repository is None:
        repository = Repository(
            project_id=project.id,
            source=scan.source,
            root_path=scan.root,
            from_zip=scan.from_zip,
        )
        session.add(repository)
        session.flush()
    else:
        repository.root_path = scan.root
        repository.from_zip = scan.from_zip

    graph_summary = graph.summary() if graph else {}
    parse_errors = parse_result.parse_errors if parse_result else []
    run = AnalysisRun(
        repository_id=repository.id,
        status="completed_with_errors" if parse_errors else "completed",
        completed_at=datetime.now(timezone.utc),
        file_count=scan.total_files,
        java_file_count=len(scan.java_files),
        parsed_file_count=parse_result.files_parsed if parse_result else 0,
        failed_file_count=parse_result.files_failed if parse_result else 0,
        graph_node_count=len(graph.nodes) if graph else 0,
        graph_edge_count=len(graph.edges) if graph else 0,
        summary_json={
            "scan": {
                "files": scan.total_files,
                "java_files": len(scan.java_files),
                "configuration_files": len(scan.configuration_files),
                "sql_files": len(scan.sql_files),
                "documentation_files": len(scan.documentation_files),
                "ignored_dirs": scan.ignored_dirs,
            },
            "parse": {
                "files_parsed": parse_result.files_parsed if parse_result else 0,
                "files_failed": parse_result.files_failed if parse_result else 0,
                "packages": len(parse_result.packages) if parse_result else 0,
                "classes": len(parse_result.classes) if parse_result else 0,
                "interfaces": len(parse_result.interfaces) if parse_result else 0,
                "methods": len(parse_result.methods) if parse_result else 0,
                "endpoints": len(parse_result.endpoints) if parse_result else 0,
                "database_references": len(parse_result.database_references) if parse_result else 0,
            },
            "graph": graph_summary,
        },
        errors_json=parse_errors,
    )
    session.add(run)
    session.flush()

    file_rows: dict[str, FileRecordRow] = {}
    for scanned_file in scan.files:
        row = FileRecordRow(
            repository_id=repository.id,
            analysis_run_id=run.id,
            relative_path=scanned_file.relative_path,
            absolute_path=scanned_file.path,
            size_bytes=scanned_file.size_bytes,
            categories_json=scanned_file.categories,
        )
        session.add(row)
        file_rows[scanned_file.relative_path] = row
    session.flush()

    def file_for(path: str | None) -> FileRecordRow | None:
        return file_rows.get(_path_key(path) or "")

    package_rows: dict[str, Package] = {}
    for package_name in (parse_result.packages if parse_result else []):
        row = Package(analysis_run_id=run.id, name=package_name)
        session.add(row)
        package_rows[package_name] = row
    session.flush()

    symbols = _iter_symbols(parse_result) if parse_result else []
    class_rows_by_qname: dict[str, ClassSymbol] = {}
    for symbol in symbols:
        source = symbol.source
        start_line, end_line = _source_lines(source)
        row = ClassSymbol(
            analysis_run_id=run.id,
            file_id=(file_for(source.file_path).id if file_for(source.file_path) else None),
            package_id=(package_rows[symbol.package].id if symbol.package in package_rows else None),
            name=symbol.name,
            qualified_name=symbol.qualified_name,
            kind=symbol.kind,
            modifiers_json=symbol.modifiers,
            annotations_json=[annotation.to_dict() for annotation in symbol.annotations],
            extends_json=symbol.extends,
            implements_json=symbol.implements,
            start_line=start_line,
            end_line=end_line,
        )
        session.add(row)
        class_rows_by_qname[symbol.qualified_name] = row
    session.flush()

    for symbol in symbols:
        class_row = class_rows_by_qname[symbol.qualified_name]
        for method_info in symbol.methods + symbol.constructors:
            start_line, end_line = _source_lines(method_info.source)
            session.add(
                MethodRow(
                    analysis_run_id=run.id,
                    class_id=class_row.id,
                    name=method_info.name,
                    signature=method_info.signature,
                    return_type=method_info.return_type,
                    parameters_json=[parameter.to_dict() for parameter in method_info.parameters],
                    modifiers_json=method_info.modifiers,
                    annotations_json=[annotation.to_dict() for annotation in method_info.annotations],
                    throws_json=method_info.throws,
                    calls_json=[call.to_dict() for call in method_info.method_calls],
                    is_constructor=method_info.is_constructor,
                    start_line=start_line,
                    end_line=end_line,
                )
            )
        for field_info in symbol.fields:
            start_line, end_line = _source_lines(field_info.source)
            session.add(
                FieldRow(
                    analysis_run_id=run.id,
                    class_id=class_row.id,
                    name=field_info.name,
                    type_name=field_info.type_name,
                    modifiers_json=field_info.modifiers,
                    annotations_json=[annotation.to_dict() for annotation in field_info.annotations],
                    start_line=start_line,
                    end_line=end_line,
                )
            )

    if parse_result:
        for parsed_file in parse_result.files:
            file_row = file_for(parsed_file.file_path)
            if not file_row or parsed_file.parse_error:
                continue
            for imported in parsed_file.imports:
                start_line, _ = _source_lines(imported.source)
                session.add(
                    ImportRecord(
                        analysis_run_id=run.id,
                        file_id=file_row.id,
                        path=imported.path,
                        is_static=imported.is_static,
                        is_wildcard=imported.is_wildcard,
                        start_line=start_line,
                    )
                )
            for endpoint in parsed_file.endpoints:
                start_line, end_line = _source_lines(endpoint.source)
                handler_class = class_rows_by_qname.get(endpoint.handler_class)
                session.add(
                    ApiEndpoint(
                        analysis_run_id=run.id,
                        file_id=file_row.id,
                        class_id=handler_class.id if handler_class else None,
                        http_method=endpoint.http_method,
                        path=endpoint.path,
                        handler_class=endpoint.handler_class,
                        handler_method=endpoint.handler_method,
                        annotations_json=[annotation.to_dict() for annotation in endpoint.annotations],
                        start_line=start_line,
                        end_line=end_line,
                    )
                )
            for reference in parsed_file.database_references:
                start_line, end_line = _source_lines(reference.source)
                owner = class_rows_by_qname.get(reference.owning_type)
                session.add(
                    DatabaseReferenceRow(
                        analysis_run_id=run.id,
                        file_id=file_row.id,
                        class_id=owner.id if owner else None,
                        kind=reference.kind,
                        name=reference.name,
                        owning_type=reference.owning_type,
                        details_json=reference.details,
                        start_line=start_line,
                        end_line=end_line,
                    )
                )

    if graph:
        for node in graph.nodes:
            session.add(
                GraphNodeRow(
                    analysis_run_id=run.id,
                    graph_id=node.id,
                    kind=node.kind,
                    name=node.name,
                    qualified_name=node.qualified_name,
                    file_path=node.file_path,
                    metadata_json=node.metadata,
                )
            )
        session.flush()
        for edge in graph.edges:
            relationship = edge.relationship.value
            session.add(
                GraphEdgeRow(
                    analysis_run_id=run.id,
                    source_graph_id=edge.source_id,
                    target_graph_id=edge.target_id,
                    relationship=relationship,
                    resolved=edge.resolved,
                    metadata_json=edge.metadata,
                )
            )
            if relationship == "DEPENDS_ON":
                session.add(
                    Dependency(
                        analysis_run_id=run.id,
                        source_graph_id=edge.source_id,
                        target_graph_id=edge.target_id,
                        relationship=relationship,
                        resolved=edge.resolved,
                        details_json=edge.metadata,
                    )
                )

    session.flush()

    try:
        from app.retrieval.indexer import index_analysis_run

        index_analysis_run(session, run.id)
    except Exception as e:
        logger.warning("Automatic semantic indexing for run %s failed: %s", run.id, e)

    session.flush()
    return PersistedAnalysis(project.id, repository.id, run.id)
