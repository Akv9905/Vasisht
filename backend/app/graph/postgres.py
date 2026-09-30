"""PostgreSQL-backed software knowledge graph service (P5).

Builds and traverses the software knowledge graph persisted in PostgreSQL.
Provides:
- Direct neighbor queries backed by PostgreSQL
- Upstream and downstream dependency discovery
- Bounded depth-limited graph traversal
- Shortest paths between codebase symbols
- Request-flow tracing from HTTP endpoint through Controller, Service, and Repository to Database
- Change-impact analysis for affected classes, methods, endpoints, and tests
- Architecture relationship verification: Controller -> Service -> Repository -> Table
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.graph.models import DependencyGraph, GraphEdge, GraphNode, RelationshipType
from app.graph.traversal import (
    ArchitectureChain,
    ImpactResult,
    NeighborInfo,
    RequestFlowResult,
    ShortestPathResult,
    TraversalDirection,
    TraversalResult,
    bounded_traversal,
    find_shortest_path,
    get_direct_neighbors,
    get_downstream_dependencies,
    get_upstream_dependencies,
    impact_traversal,
    trace_request_flow,
    verify_controller_service_repository,
)
from app.models import (
    AnalysisRun,
    GraphEdge as GraphEdgeRow,
    GraphNode as GraphNodeRow,
)


def _row_to_node(row: GraphNodeRow) -> GraphNode:
    return GraphNode(
        id=row.graph_id,
        kind=row.kind,
        name=row.name,
        qualified_name=row.qualified_name,
        file_path=row.file_path,
        metadata=dict(row.metadata_json or {}),
    )


def _row_to_edge(row: GraphEdgeRow) -> GraphEdge:
    # Safely convert relationship string to enum or preserve value
    try:
        rel = RelationshipType(row.relationship)
    except (ValueError, KeyError):
        rel = row.relationship  # type: ignore[assignment]

    return GraphEdge(
        source_id=row.source_graph_id,
        target_id=row.target_graph_id,
        relationship=rel,
        resolved=row.resolved,
        metadata=dict(row.metadata_json or {}),
    )


class PostgresKnowledgeGraph:
    """Knowledge graph loaded from and backed by PostgreSQL database tables."""

    def __init__(self, session: Session, analysis_run_id: int | None = None) -> None:
        self.session = session
        if analysis_run_id is not None:
            self.analysis_run_id = analysis_run_id
        else:
            # Auto-select the latest completed run
            latest_run = self.session.scalar(
                select(AnalysisRun)
                .where(AnalysisRun.status.in_(["completed", "completed_with_errors"]))
                .order_by(AnalysisRun.id.desc())
                .limit(1)
            )
            if latest_run is None:
                raise ValueError("No analysis runs found in database. Run analyze --persist first.")
            self.analysis_run_id = latest_run.id

        self._graph: DependencyGraph | None = None

    def load_graph(self, force_reload: bool = False) -> DependencyGraph:
        """Load the entire knowledge graph for this run into an in-memory DependencyGraph."""
        if self._graph is not None and not force_reload:
            return self._graph

        node_rows = self.session.scalars(
            select(GraphNodeRow).where(GraphNodeRow.analysis_run_id == self.analysis_run_id)
        ).all()
        edge_rows = self.session.scalars(
            select(GraphEdgeRow).where(GraphEdgeRow.analysis_run_id == self.analysis_run_id)
        ).all()

        nodes = [_row_to_node(r) for r in node_rows]
        edges = [_row_to_edge(r) for r in edge_rows]

        self._graph = DependencyGraph(nodes=nodes, edges=edges)
        return self._graph

    def get_node(self, node_id: str) -> GraphNode | None:
        """Retrieve a specific node from PostgreSQL."""
        row = self.session.scalar(
            select(GraphNodeRow).where(
                GraphNodeRow.analysis_run_id == self.analysis_run_id,
                GraphNodeRow.graph_id == node_id,
            )
        )
        return _row_to_node(row) if row else None

    def find_nodes(
        self,
        *,
        kind: str | None = None,
        name: str | None = None,
        query: str | None = None,
    ) -> list[GraphNode]:
        """Query nodes in PostgreSQL by kind, name, or search query."""
        stmt = select(GraphNodeRow).where(GraphNodeRow.analysis_run_id == self.analysis_run_id)
        if kind is not None:
            stmt = stmt.where(GraphNodeRow.kind == kind)
        if name is not None:
            stmt = stmt.where(GraphNodeRow.name == name)
        if query is not None:
            stmt = stmt.where(
                GraphNodeRow.name.ilike(f"%{query}%")
                | GraphNodeRow.qualified_name.ilike(f"%{query}%")
                | GraphNodeRow.graph_id.ilike(f"%{query}%")
            )

        rows = self.session.scalars(stmt).all()
        return [_row_to_node(r) for r in rows]

    def get_neighbors(
        self,
        node_id: str,
        direction: TraversalDirection = "both",
        relationship: str | RelationshipType | None = None,
    ) -> list[NeighborInfo]:
        """Get direct neighbors of a node using PostgreSQL graph edges."""
        graph = self.load_graph()
        return get_direct_neighbors(
            graph,
            node_id,
            direction=direction,
            relationship=relationship,
        )

    def get_upstream_dependencies(
        self,
        node_id: str,
        max_depth: int = 1,
        relationships: list[str] | None = None,
    ) -> TraversalResult:
        """Find upstream dependencies (callers/dependents) up to max_depth."""
        graph = self.load_graph()
        return get_upstream_dependencies(
            graph,
            node_id,
            max_depth=max_depth,
            relationships=relationships,
        )

    def get_downstream_dependencies(
        self,
        node_id: str,
        max_depth: int = 1,
        relationships: list[str] | None = None,
    ) -> TraversalResult:
        """Find downstream dependencies (callees/dependencies) up to max_depth."""
        graph = self.load_graph()
        return get_downstream_dependencies(
            graph,
            node_id,
            max_depth=max_depth,
            relationships=relationships,
        )

    def bounded_traversal(
        self,
        start_id: str,
        max_depth: int = 3,
        direction: TraversalDirection = "outgoing",
        relationships: list[str] | None = None,
        filter_kinds: list[str] | None = None,
    ) -> TraversalResult:
        """Perform bounded traversal starting from a node."""
        graph = self.load_graph()
        return bounded_traversal(
            graph,
            start_id,
            max_depth=max_depth,
            direction=direction,
            relationships=relationships,
            filter_kinds=filter_kinds,
        )

    def find_shortest_path(
        self,
        source_id: str,
        target_id: str,
        direction: TraversalDirection = "outgoing",
        relationships: list[str] | None = None,
    ) -> ShortestPathResult | None:
        """Find the shortest path between two nodes in the graph."""
        graph = self.load_graph()
        return find_shortest_path(
            graph,
            source_id=source_id,
            target_id=target_id,
            direction=direction,
            relationships=relationships,
        )

    def trace_request_flow(
        self,
        endpoint_or_path: str,
        max_depth: int = 10,
    ) -> RequestFlowResult:
        """Trace request execution flow from an endpoint or controller down to the database."""
        graph = self.load_graph()
        return trace_request_flow(
            graph,
            endpoint_or_path=endpoint_or_path,
            max_depth=max_depth,
        )

    def impact_traversal(
        self,
        target_symbol: str,
        max_depth: int = 5,
    ) -> ImpactResult:
        """Perform change-impact traversal for a target symbol."""
        graph = self.load_graph()
        return impact_traversal(
            graph,
            target_symbol=target_symbol,
            max_depth=max_depth,
        )

    def verify_controller_service_repository(self) -> list[ArchitectureChain]:
        """Verify Controller -> Service -> Repository -> Database relationships in PostgreSQL."""
        graph = self.load_graph()
        return verify_controller_service_repository(graph)
