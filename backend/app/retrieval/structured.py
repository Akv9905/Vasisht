"""Structured codebase retrieval engine (P7).

Retrieves software symbols, source locations, call chains, dependencies,
APIs, and architectural flow paths directly from PostgreSQL data and the
knowledge graph without requiring embeddings or an LLM.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.graph.postgres import PostgresKnowledgeGraph
from app.graph.traversal import RequestFlowResult, trace_request_flow
from app.models import (
    AnalysisRun,
    ApiEndpoint,
    ClassSymbol,
    DatabaseReference,
    Field as FieldRow,
    FileRecord,
    GraphEdge,
    GraphNode,
    ImportRecord,
    Method,
    Package,
)


@dataclass
class SourceLocation:
    """Precise source code location of a retrieved symbol."""

    file_path: str
    start_line: int | None = None
    end_line: int | None = None
    relative_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RetrievedFile:
    id: int
    relative_path: str
    absolute_path: str | None
    size_bytes: int
    categories: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RetrievedPackage:
    id: int
    name: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RetrievedClass:
    id: int
    name: str
    qualified_name: str
    kind: str
    package: str | None
    file_path: str | None
    location: SourceLocation
    annotations: list[dict[str, Any]]
    extends: list[str]
    implements: list[str]
    method_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RetrievedMethod:
    id: int
    name: str
    class_name: str
    signature: str
    return_type: str | None
    location: SourceLocation
    annotations: list[dict[str, Any]]
    calls: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RetrievedEndpoint:
    id: int
    http_method: str
    path: str
    handler_class: str
    handler_method: str
    location: SourceLocation
    annotations: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RetrievedDatabaseReference:
    id: int
    kind: str
    name: str
    owning_type: str
    location: SourceLocation
    details: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RetrievedCallerCallee:
    caller_symbol: str
    caller_kind: str
    caller_file: str | None
    caller_lines: tuple[int | None, int | None]
    callee_symbol: str
    callee_kind: str
    callee_file: str | None
    relationship: str
    resolved: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FlowStep:
    step: int
    role: str  # Endpoint, Controller, Service, Repository, Database
    symbol: str
    kind: str
    file_path: str
    lines: tuple[int | None, int | None]
    relationship_to_next: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class StructuredFlowRetrievalResult:
    """Structured architectural retrieval linking Controller -> Service -> Repository -> Database."""

    endpoint: str
    controller: str
    service: str
    repository: str
    database: str | None
    steps: list[FlowStep]
    evidence: list[dict[str, Any]]
    reaches_database: bool

    def summary_lines(self) -> list[str]:
        lines = [
            f"Structured Flow Retrieval for: {self.endpoint}",
            f"  Controller : {self.controller}",
            f"  Service    : {self.service}",
            f"  Repository : {self.repository}",
            f"  Database   : {self.database or 'None'}",
            "",
            "Steps:",
        ]
        for s in self.steps:
            rel = f" --[{s.relationship_to_next}]-->" if s.relationship_to_next else ""
            lines.append(f"  {s.step}. [{s.role}] {s.symbol} ({s.file_path}:{s.lines[0] or '?'}){rel}")
        return lines

    def to_dict(self) -> dict[str, Any]:
        return {
            "endpoint": self.endpoint,
            "controller": self.controller,
            "service": self.service,
            "repository": self.repository,
            "database": self.database,
            "reaches_database": self.reaches_database,
            "steps": [s.to_dict() for s in self.steps],
            "evidence": self.evidence,
        }


class StructuredRetriever:
    """Executes structured queries against PostgreSQL tables and the knowledge graph."""

    def __init__(self, session: Session, analysis_run_id: int | None = None) -> None:
        self.session = session
        if analysis_run_id is not None:
            self.analysis_run_id = analysis_run_id
        else:
            latest_run = self.session.scalar(
                select(AnalysisRun)
                .where(AnalysisRun.status.in_(["completed", "completed_with_errors"]))
                .order_by(AnalysisRun.id.desc())
                .limit(1)
            )
            if latest_run is None:
                raise ValueError("No analysis runs found in database. Run analyze --persist first.")
            self.analysis_run_id = latest_run.id

        self._kg = PostgresKnowledgeGraph(session, self.analysis_run_id)

    # 1. Retrieve Files
    def retrieve_files(
        self, query: str | None = None, category: str | None = None
    ) -> list[RetrievedFile]:
        stmt = select(FileRecord).where(FileRecord.analysis_run_id == self.analysis_run_id)
        if query:
            stmt = stmt.where(FileRecord.relative_path.ilike(f"%{query}%"))
        rows = self.session.scalars(stmt).all()
        results: list[RetrievedFile] = []
        for r in rows:
            cats = list(r.categories_json or [])
            if category and category not in cats:
                continue
            results.append(
                RetrievedFile(
                    id=r.id,
                    relative_path=r.relative_path,
                    absolute_path=r.absolute_path,
                    size_bytes=r.size_bytes,
                    categories=cats,
                )
            )
        return results

    # 2. Retrieve Packages
    def retrieve_packages(self, query: str | None = None) -> list[RetrievedPackage]:
        stmt = select(Package).where(Package.analysis_run_id == self.analysis_run_id)
        if query:
            stmt = stmt.where(Package.name.ilike(f"%{query}%"))
        rows = self.session.scalars(stmt).all()
        return [RetrievedPackage(id=r.id, name=r.name) for r in rows]

    # 3. Retrieve Classes & Interfaces
    def retrieve_classes(
        self,
        query: str | None = None,
        kind: str | None = None,
        package: str | None = None,
        annotation: str | None = None,
    ) -> list[RetrievedClass]:
        stmt = (
            select(ClassSymbol, FileRecord, Package)
            .outerjoin(FileRecord, ClassSymbol.file_id == FileRecord.id)
            .outerjoin(Package, ClassSymbol.package_id == Package.id)
            .where(ClassSymbol.analysis_run_id == self.analysis_run_id)
        )
        if query:
            stmt = stmt.where(
                ClassSymbol.name.ilike(f"%{query}%")
                | ClassSymbol.qualified_name.ilike(f"%{query}%")
            )
        if kind:
            stmt = stmt.where(ClassSymbol.kind == kind)

        rows = self.session.execute(stmt).all()
        results: list[RetrievedClass] = []
        for cls_row, file_row, pkg_row in rows:
            pkg_name = pkg_row.name if pkg_row else None
            if package and pkg_name != package:
                continue

            annotations = list(cls_row.annotations_json or [])
            if annotation:
                ann_names = [a.get("name", "") for a in annotations]
                if annotation.lstrip("@") not in ann_names:
                    continue

            # Count methods for class
            method_count = self.session.scalar(
                select(func.count(Method.id)).where(Method.class_id == cls_row.id)
            ) or 0

            file_p = file_row.relative_path if file_row else "unknown"
            loc = SourceLocation(
                file_path=file_p,
                start_line=cls_row.start_line,
                end_line=cls_row.end_line,
                relative_path=file_p,
            )

            results.append(
                RetrievedClass(
                    id=cls_row.id,
                    name=cls_row.name,
                    qualified_name=cls_row.qualified_name,
                    kind=cls_row.kind,
                    package=pkg_name,
                    file_path=file_p,
                    location=loc,
                    annotations=annotations,
                    extends=list(cls_row.extends_json or []),
                    implements=list(cls_row.implements_json or []),
                    method_count=method_count,
                )
            )
        return results

    # 4. Retrieve Methods
    def retrieve_methods(
        self,
        query: str | None = None,
        class_name: str | None = None,
        annotation: str | None = None,
    ) -> list[RetrievedMethod]:
        stmt = (
            select(Method, ClassSymbol, FileRecord)
            .join(ClassSymbol, Method.class_id == ClassSymbol.id)
            .outerjoin(FileRecord, ClassSymbol.file_id == FileRecord.id)
            .where(Method.analysis_run_id == self.analysis_run_id)
        )
        if query:
            stmt = stmt.where(
                Method.name.ilike(f"%{query}%") | Method.signature.ilike(f"%{query}%")
            )
        if class_name:
            stmt = stmt.where(ClassSymbol.name == class_name)

        rows = self.session.execute(stmt).all()
        results: list[RetrievedMethod] = []
        for m_row, c_row, f_row in rows:
            annotations = list(m_row.annotations_json or [])
            if annotation:
                ann_names = [a.get("name", "") for a in annotations]
                if annotation.lstrip("@") not in ann_names:
                    continue

            file_p = f_row.relative_path if f_row else "unknown"
            loc = SourceLocation(
                file_path=file_p,
                start_line=m_row.start_line,
                end_line=m_row.end_line,
                relative_path=file_p,
            )
            results.append(
                RetrievedMethod(
                    id=m_row.id,
                    name=m_row.name,
                    class_name=c_row.name,
                    signature=m_row.signature,
                    return_type=m_row.return_type,
                    location=loc,
                    annotations=annotations,
                    calls=list(m_row.calls_json or []),
                )
            )
        return results

    # 5. Retrieve APIs / Endpoints
    def retrieve_endpoints(
        self,
        http_method: str | None = None,
        path: str | None = None,
        handler: str | None = None,
    ) -> list[RetrievedEndpoint]:
        stmt = (
            select(ApiEndpoint, FileRecord)
            .outerjoin(FileRecord, ApiEndpoint.file_id == FileRecord.id)
            .where(ApiEndpoint.analysis_run_id == self.analysis_run_id)
        )
        if http_method:
            stmt = stmt.where(ApiEndpoint.http_method == http_method.upper())
        if path:
            stmt = stmt.where(ApiEndpoint.path.ilike(f"%{path}%"))
        if handler:
            stmt = stmt.where(ApiEndpoint.handler_class.ilike(f"%{handler}%"))

        rows = self.session.execute(stmt).all()
        results: list[RetrievedEndpoint] = []
        for ep_row, f_row in rows:
            file_p = f_row.relative_path if f_row else "unknown"
            loc = SourceLocation(
                file_path=file_p,
                start_line=ep_row.start_line,
                end_line=ep_row.end_line,
                relative_path=file_p,
            )
            results.append(
                RetrievedEndpoint(
                    id=ep_row.id,
                    http_method=ep_row.http_method,
                    path=ep_row.path,
                    handler_class=ep_row.handler_class,
                    handler_method=ep_row.handler_method,
                    location=loc,
                    annotations=list(ep_row.annotations_json or []),
                )
            )
        return results

    # 6. Retrieve Database References
    def retrieve_database_references(
        self,
        kind: str | None = None,
        name: str | None = None,
        owning_type: str | None = None,
    ) -> list[RetrievedDatabaseReference]:
        stmt = (
            select(DatabaseReference, FileRecord)
            .outerjoin(FileRecord, DatabaseReference.file_id == FileRecord.id)
            .where(DatabaseReference.analysis_run_id == self.analysis_run_id)
        )
        if kind:
            stmt = stmt.where(DatabaseReference.kind == kind)
        if name:
            stmt = stmt.where(DatabaseReference.name.ilike(f"%{name}%"))
        if owning_type:
            stmt = stmt.where(DatabaseReference.owning_type.ilike(f"%{owning_type}%"))

        rows = self.session.execute(stmt).all()
        results: list[RetrievedDatabaseReference] = []
        for db_row, f_row in rows:
            file_p = f_row.relative_path if f_row else "unknown"
            loc = SourceLocation(
                file_path=file_p,
                start_line=db_row.start_line,
                end_line=db_row.end_line,
                relative_path=file_p,
            )
            results.append(
                RetrievedDatabaseReference(
                    id=db_row.id,
                    kind=db_row.kind,
                    name=db_row.name,
                    owning_type=db_row.owning_type,
                    location=loc,
                    details=dict(db_row.details_json or {}),
                )
            )
        return results

    # 7. Retrieve Callers and Callees
    def retrieve_callers(self, target_symbol: str) -> list[RetrievedCallerCallee]:
        """Find all callers of a method or class."""
        stmt = select(GraphEdge).where(
            GraphEdge.analysis_run_id == self.analysis_run_id,
            GraphEdge.relationship.in_(["CALLS", "DEPENDS_ON"]),
            GraphEdge.target_graph_id.ilike(f"%{target_symbol}%"),
        )
        edges = self.session.scalars(stmt).all()
        results: list[RetrievedCallerCallee] = []
        for e in edges:
            src_node = self._kg.get_node(e.source_graph_id)
            tgt_node = self._kg.get_node(e.target_graph_id)
            results.append(
                RetrievedCallerCallee(
                    caller_symbol=src_node.name if src_node else e.source_graph_id,
                    caller_kind=src_node.kind if src_node else "unknown",
                    caller_file=src_node.file_path if src_node else None,
                    caller_lines=(src_node.metadata.get("start_line"), src_node.metadata.get("end_line")) if src_node else (None, None),
                    callee_symbol=tgt_node.name if tgt_node else e.target_graph_id,
                    callee_kind=tgt_node.kind if tgt_node else "unknown",
                    callee_file=tgt_node.file_path if tgt_node else None,
                    relationship=e.relationship,
                    resolved=e.resolved,
                )
            )
        return results

    def retrieve_callees(self, source_symbol: str) -> list[RetrievedCallerCallee]:
        """Find all callees / dependencies of a method or class."""
        stmt = select(GraphEdge).where(
            GraphEdge.analysis_run_id == self.analysis_run_id,
            GraphEdge.relationship.in_(["CALLS", "DEPENDS_ON", "QUERIES", "REFERENCES"]),
            GraphEdge.source_graph_id.ilike(f"%{source_symbol}%"),
        )
        edges = self.session.scalars(stmt).all()
        results: list[RetrievedCallerCallee] = []
        for e in edges:
            src_node = self._kg.get_node(e.source_graph_id)
            tgt_node = self._kg.get_node(e.target_graph_id)
            results.append(
                RetrievedCallerCallee(
                    caller_symbol=src_node.name if src_node else e.source_graph_id,
                    caller_kind=src_node.kind if src_node else "unknown",
                    caller_file=src_node.file_path if src_node else None,
                    caller_lines=(src_node.metadata.get("start_line"), src_node.metadata.get("end_line")) if src_node else (None, None),
                    callee_symbol=tgt_node.name if tgt_node else e.target_graph_id,
                    callee_kind=tgt_node.kind if tgt_node else "unknown",
                    callee_file=tgt_node.file_path if tgt_node else None,
                    relationship=e.relationship,
                    resolved=e.resolved,
                )
            )
        return results

    # 8. Retrieve Source Location of a Symbol
    def retrieve_source_location(self, symbol_name: str) -> SourceLocation | None:
        # Check ClassSymbol
        cls = self.session.scalar(
            select(ClassSymbol).where(
                ClassSymbol.analysis_run_id == self.analysis_run_id,
                ClassSymbol.name == symbol_name,
            )
        )
        if cls:
            f = self.session.scalar(select(FileRecord).where(FileRecord.id == cls.file_id))
            file_p = f.relative_path if f else "unknown"
            return SourceLocation(file_path=file_p, start_line=cls.start_line, end_line=cls.end_line)

        # Check Method
        m = self.session.scalar(
            select(Method).where(
                Method.analysis_run_id == self.analysis_run_id,
                Method.name == symbol_name,
            )
        )
        if m:
            c = self.session.scalar(select(ClassSymbol).where(ClassSymbol.id == m.class_id))
            f = self.session.scalar(select(FileRecord).where(FileRecord.id == c.file_id)) if c else None
            file_p = f.relative_path if f else "unknown"
            return SourceLocation(file_path=file_p, start_line=m.start_line, end_line=m.end_line)

        # Check GraphNode
        node = self._kg.get_node(symbol_name) or self.session.scalar(
            select(GraphNode).where(
                GraphNode.analysis_run_id == self.analysis_run_id,
                GraphNode.name == symbol_name,
            )
        )
        if node and node.file_path:
            return SourceLocation(file_path=node.file_path)

        return None

    # 9. Architectural Flow Retrieval: "How does /api/payment reach the database?"
    def retrieve_flow(self, query_or_endpoint: str) -> StructuredFlowRetrievalResult | None:
        """Retrieve complete architectural flow: Controller -> Service -> Repository -> Database."""
        # Extract endpoint path from query string or direct path
        match = re.search(r"(/api/[a-zA-Z0-9_\-\/\{\}]+)", query_or_endpoint)
        target_path = match.group(1) if match else query_or_endpoint.strip()

        # Find matching endpoint in PostgreSQL
        ep = self.session.scalar(
            select(ApiEndpoint).where(
                ApiEndpoint.analysis_run_id == self.analysis_run_id,
                ApiEndpoint.path.ilike(f"%{target_path}%"),
            )
        )
        if not ep:
            # Fallback: check endpoints by partial match
            all_eps = self.session.scalars(
                select(ApiEndpoint).where(ApiEndpoint.analysis_run_id == self.analysis_run_id)
            ).all()
            for cand in all_eps:
                if cand.path in target_path or target_path in cand.path:
                    ep = cand
                    break

        if not ep:
            return None

        # Execute trace using PostgreSQL knowledge graph
        flow_result: RequestFlowResult = self._kg.trace_request_flow(ep.path)

        # Map steps to architectural roles
        steps: list[FlowStep] = []
        controller_name = ep.handler_class.split(".")[-1]
        service_name = "UnknownService"
        repository_name = "UnknownRepository"
        database_table = flow_result.database_table

        evidence: list[dict[str, Any]] = []

        for i, st in enumerate(flow_result.steps, start=1):
            role = "Component"
            name_lower = st.node_name.lower()
            id_lower = st.node_id.lower()

            if st.node_kind == "endpoint":
                role = "Endpoint"
            elif "controller" in name_lower or "controller" in id_lower:
                role = "Controller"
                controller_name = st.node_name
            elif "service" in name_lower or "service" in id_lower:
                role = "Service"
                if "test" not in name_lower:
                    service_name = st.node_name
            elif "repository" in name_lower or "repository" in id_lower:
                role = "Repository"
                repository_name = st.node_name
            elif st.node_kind == "database_table" or "table:" in id_lower:
                role = "Database"
                database_table = st.node_name

            rel_next = flow_result.steps[i].relationship if i < len(flow_result.steps) else None

            start_l = st.details.get("start_line")
            end_l = st.details.get("end_line")

            if start_l is None:
                if st.node_kind == "method":
                    m_row = self.session.scalar(
                        select(Method).where(
                            Method.analysis_run_id == self.analysis_run_id,
                            Method.name == st.node_name,
                        )
                    )
                    if m_row:
                        start_l, end_l = m_row.start_line, m_row.end_line
                elif st.node_kind in ("class", "interface"):
                    c_row = self.session.scalar(
                        select(ClassSymbol).where(
                            ClassSymbol.analysis_run_id == self.analysis_run_id,
                            ClassSymbol.name == st.node_name,
                        )
                    )
                    if c_row:
                        start_l, end_l = c_row.start_line, c_row.end_line
                elif st.node_kind == "endpoint":
                    ep_row = self.session.scalar(
                        select(ApiEndpoint).where(
                            ApiEndpoint.analysis_run_id == self.analysis_run_id,
                            ApiEndpoint.path == ep.path,
                        )
                    )
                    if ep_row:
                        start_l, end_l = ep_row.start_line, ep_row.end_line
                elif st.node_kind == "database_table":
                    db_row = self.session.scalar(
                        select(DatabaseReference).where(
                            DatabaseReference.analysis_run_id == self.analysis_run_id,
                            DatabaseReference.name == st.node_name,
                        )
                    )
                    if db_row:
                        start_l, end_l = db_row.start_line, db_row.end_line

            step_obj = FlowStep(
                step=i,
                role=role,
                symbol=st.node_name,
                kind=st.node_kind,
                file_path=st.file_path or "unknown",
                lines=(start_l, end_l),
                relationship_to_next=rel_next,
            )
            steps.append(step_obj)

            evidence.append({
                "role": role,
                "symbol": st.node_name,
                "kind": st.node_kind,
                "file_path": st.file_path,
                "start_line": start_l,
                "end_line": end_l,
                "details": st.details,
            })

        return StructuredFlowRetrievalResult(
            endpoint=ep.path,
            controller=controller_name,
            service=service_name,
            repository=repository_name,
            database=database_table,
            steps=steps,
            evidence=evidence,
            reaches_database=flow_result.reaches_database,
        )
