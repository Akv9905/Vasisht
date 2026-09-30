"""Software knowledge graph traversal algorithms and data models (P5).

Supports:
- direct neighbors (incoming, outgoing, both)
- upstream dependencies (incoming callers/dependents)
- downstream dependencies (outgoing callees/dependencies)
- bounded traversal (depth-limited BFS with cycle protection)
- shortest relevant paths between software entities
- request-flow tracing (endpoint -> controller -> service -> repository -> database)
- change impact traversal (affected callers, controllers, endpoints, tests)
- architectural relationship verification (Controller -> Service -> Repository -> Table)
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal

from app.graph.models import DependencyGraph, GraphEdge, GraphNode, RelationshipType

TraversalDirection = Literal["outgoing", "incoming", "both"]


@dataclass
class NeighborInfo:
    """A neighboring node and the connecting edge."""

    node: GraphNode
    edge: GraphEdge
    direction: Literal["outgoing", "incoming"]

    def to_dict(self) -> dict[str, Any]:
        return {
            "node": self.node.to_dict(),
            "edge": self.edge.to_dict(),
            "direction": self.direction,
        }


@dataclass
class TraversalResult:
    """Result of a bounded graph traversal."""

    start_node_id: str
    visited_nodes: list[GraphNode]
    visited_edges: list[GraphEdge]
    max_depth_reached: int
    depth_map: dict[str, int]
    paths: list[list[str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "start_node_id": self.start_node_id,
            "total_nodes": len(self.visited_nodes),
            "total_edges": len(self.visited_edges),
            "max_depth_reached": self.max_depth_reached,
            "depth_map": self.depth_map,
            "nodes": [n.to_dict() for n in self.visited_nodes],
            "edges": [e.to_dict() for e in self.visited_edges],
            "paths": self.paths,
        }


@dataclass
class ShortestPathResult:
    """Shortest path between two nodes in the knowledge graph."""

    source_id: str
    target_id: str
    length: int
    nodes: list[GraphNode]
    edges: list[GraphEdge]

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "length": self.length,
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
        }


@dataclass
class RequestFlowStep:
    """Single step in a request execution flow."""

    step_number: int
    node_id: str
    node_kind: str
    node_name: str
    qualified_name: str | None = None
    file_path: str | None = None
    relationship: str | None = None
    target_id: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    unresolved_calls: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_number": self.step_number,
            "node_id": self.node_id,
            "node_kind": self.node_kind,
            "node_name": self.node_name,
            "qualified_name": self.qualified_name,
            "file_path": self.file_path,
            "relationship": self.relationship,
            "target_id": self.target_id,
            "details": self.details,
            "unresolved_calls": self.unresolved_calls,
        }


@dataclass
class RequestFlowResult:
    """Complete traced request flow from HTTP endpoint to database."""

    endpoint: str
    steps: list[RequestFlowStep]
    reaches_database: bool
    database_table: str | None = None
    unresolved_steps: list[str] = field(default_factory=list)

    def summary_lines(self) -> list[str]:
        lines = [f"Request Flow for: {self.endpoint}"]
        for step in self.steps:
            rel = f" --[{step.relationship}]--> " if step.relationship else " "
            lines.append(f"  {step.step_number}. [{step.node_kind}] {step.node_name}{rel}")
        if self.reaches_database:
            lines.append(f"  [OK] Reaches database table: {self.database_table}")
        else:
            lines.append("  [!] Does not reach a database table")
        if self.unresolved_steps:
            lines.append(f"  Unresolved calls: {', '.join(self.unresolved_steps)}")
        return lines

    def to_dict(self) -> dict[str, Any]:
        return {
            "endpoint": self.endpoint,
            "total_steps": len(self.steps),
            "reaches_database": self.reaches_database,
            "database_table": self.database_table,
            "unresolved_steps": self.unresolved_steps,
            "steps": [s.to_dict() for s in self.steps],
        }


@dataclass
class ImpactResult:
    """Result of change-impact traversal for a target symbol."""

    target_id: str
    target_name: str
    target_kind: str
    max_depth: int
    affected_nodes: list[GraphNode]
    affected_by_depth: dict[int, list[GraphNode]]
    affected_callers: list[GraphNode]
    affected_controllers: list[GraphNode]
    affected_endpoints: list[GraphNode]
    affected_services: list[GraphNode]
    affected_repositories: list[GraphNode]
    affected_tests: list[GraphNode]

    def summary_lines(self) -> list[str]:
        lines = [
            f"Impact Analysis for: {self.target_name} ({self.target_kind})",
            f"  Potentially affected entities: {len(self.affected_nodes)}",
            f"  Affected Controllers: {len(self.affected_controllers)}",
            f"  Affected Endpoints: {len(self.affected_endpoints)}",
            f"  Affected Services: {len(self.affected_services)}",
            f"  Affected Repositories: {len(self.affected_repositories)}",
            f"  Affected Tests: {len(self.affected_tests)}",
        ]
        return lines

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_id": self.target_id,
            "target_name": self.target_name,
            "target_kind": self.target_kind,
            "max_depth": self.max_depth,
            "total_affected": len(self.affected_nodes),
            "affected_by_depth": {
                d: [n.to_dict() for n in nodes]
                for d, nodes in self.affected_by_depth.items()
            },
            "affected_callers": [n.to_dict() for n in self.affected_callers],
            "affected_controllers": [n.to_dict() for n in self.affected_controllers],
            "affected_endpoints": [n.to_dict() for n in self.affected_endpoints],
            "affected_services": [n.to_dict() for n in self.affected_services],
            "affected_repositories": [n.to_dict() for n in self.affected_repositories],
            "affected_tests": [n.to_dict() for n in self.affected_tests],
        }


@dataclass
class ArchitectureChain:
    """A verified Controller -> Service -> Repository -> Database relationship chain."""

    controller_node: GraphNode
    service_node: GraphNode
    repository_node: GraphNode
    table_node: GraphNode | None
    endpoint_node: GraphNode | None
    type_chain_edges: list[GraphEdge]
    call_chain_edges: list[GraphEdge]
    verified: bool = True

    def summary_line(self) -> str:
        ep = f"[{self.endpoint_node.name}] -> " if self.endpoint_node else ""
        table = f" -> [{self.table_node.name}]" if self.table_node else ""
        return (
            f"{ep}{self.controller_node.name} -> {self.service_node.name} -> "
            f"{self.repository_node.name}{table}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "controller": self.controller_node.to_dict(),
            "service": self.service_node.to_dict(),
            "repository": self.repository_node.to_dict(),
            "table": self.table_node.to_dict() if self.table_node else None,
            "endpoint": self.endpoint_node.to_dict() if self.endpoint_node else None,
            "type_chain_edges": [e.to_dict() for e in self.type_chain_edges],
            "call_chain_edges": [e.to_dict() for e in self.call_chain_edges],
            "verified": self.verified,
        }


def _rel_matches(edge_rel: Any, filter_rels: list[str] | set[str] | None) -> bool:
    if filter_rels is None:
        return True
    val = edge_rel.value if isinstance(edge_rel, Enum) else str(edge_rel)
    return val in filter_rels


def get_direct_neighbors(
    graph: DependencyGraph,
    node_id: str,
    direction: TraversalDirection = "both",
    relationship: str | RelationshipType | None = None,
) -> list[NeighborInfo]:
    """Retrieve all immediate neighbors of a node."""
    target_rel = (
        relationship.value if isinstance(relationship, Enum) else str(relationship)
    ) if relationship is not None else None

    results: list[NeighborInfo] = []

    if direction in ("outgoing", "both"):
        for edge in graph.outgoing_edges(node_id):
            if target_rel is not None:
                e_rel = edge.relationship.value if isinstance(edge.relationship, Enum) else str(edge.relationship)
                if e_rel != target_rel:
                    continue
            target_node = graph.get_node(edge.target_id)
            if target_node:
                results.append(NeighborInfo(target_node, edge, "outgoing"))

    if direction in ("incoming", "both"):
        for edge in graph.incoming_edges(node_id):
            if target_rel is not None:
                e_rel = edge.relationship.value if isinstance(edge.relationship, Enum) else str(edge.relationship)
                if e_rel != target_rel:
                    continue
            src_node = graph.get_node(edge.source_id)
            if src_node:
                results.append(NeighborInfo(src_node, edge, "incoming"))

    return results


def bounded_traversal(
    graph: DependencyGraph,
    start_id: str,
    max_depth: int = 3,
    direction: TraversalDirection = "outgoing",
    relationships: list[str] | None = None,
    filter_kinds: list[str] | None = None,
) -> TraversalResult:
    """Breadth-first traversal up to max_depth with cycle detection."""
    start_node = graph.get_node(start_id)
    if start_node is None:
        return TraversalResult(start_id, [], [], 0, {})

    rel_set = set(relationships) if relationships else None
    kind_set = set(filter_kinds) if filter_kinds else None

    visited_node_map: dict[str, GraphNode] = {start_node.id: start_node}
    visited_edges: list[GraphEdge] = []
    depth_map: dict[str, int] = {start_node.id: 0}
    paths: list[list[str]] = [[start_node.id]]

    # Queue contains (current_node_id, current_depth, current_path)
    queue: deque[tuple[str, int, list[str]]] = deque([(start_id, 0, [start_id])])
    max_depth_reached = 0

    while queue:
        curr_id, curr_depth, curr_path = queue.popleft()
        if curr_depth > max_depth_reached:
            max_depth_reached = curr_depth

        if curr_depth >= max_depth:
            continue

        neighbors = get_direct_neighbors(graph, curr_id, direction=direction)
        for n_info in neighbors:
            edge = n_info.edge
            neighbor_node = n_info.node

            if not _rel_matches(edge.relationship, rel_set):
                continue
            if kind_set is not None and neighbor_node.kind not in kind_set:
                continue

            if edge not in visited_edges:
                visited_edges.append(edge)

            next_id = neighbor_node.id
            if next_id not in depth_map:
                depth_map[next_id] = curr_depth + 1
                visited_node_map[next_id] = neighbor_node
                new_path = curr_path + [next_id]
                paths.append(new_path)
                queue.append((next_id, curr_depth + 1, new_path))

    return TraversalResult(
        start_node_id=start_id,
        visited_nodes=list(visited_node_map.values()),
        visited_edges=visited_edges,
        max_depth_reached=max_depth_reached,
        depth_map=depth_map,
        paths=paths,
    )


def get_upstream_dependencies(
    graph: DependencyGraph,
    node_id: str,
    max_depth: int = 1,
    relationships: list[str] | None = None,
) -> TraversalResult:
    """Find entities that depend on or call this node (incoming edges)."""
    return bounded_traversal(
        graph,
        node_id,
        max_depth=max_depth,
        direction="incoming",
        relationships=relationships,
    )


def get_downstream_dependencies(
    graph: DependencyGraph,
    node_id: str,
    max_depth: int = 1,
    relationships: list[str] | None = None,
) -> TraversalResult:
    """Find entities that this node depends on or calls (outgoing edges)."""
    return bounded_traversal(
        graph,
        node_id,
        max_depth=max_depth,
        direction="outgoing",
        relationships=relationships,
    )


def find_shortest_path(
    graph: DependencyGraph,
    source_id: str,
    target_id: str,
    direction: TraversalDirection = "outgoing",
    relationships: list[str] | None = None,
) -> ShortestPathResult | None:
    """Find the shortest directed path between two entities via BFS."""
    if source_id == target_id:
        src = graph.get_node(source_id)
        if src:
            return ShortestPathResult(source_id, target_id, 0, [src], [])
        return None

    src_node = graph.get_node(source_id)
    tgt_node = graph.get_node(target_id)
    if not src_node or not tgt_node:
        return None

    rel_set = set(relationships) if relationships else None

    # Queue stores: (current_id, node_list, edge_list)
    queue: deque[tuple[str, list[GraphNode], list[GraphEdge]]] = deque(
        [(source_id, [src_node], [])]
    )
    visited: set[str] = {source_id}

    while queue:
        curr_id, node_path, edge_path = queue.popleft()

        neighbors = get_direct_neighbors(graph, curr_id, direction=direction)
        for n_info in neighbors:
            edge = n_info.edge
            neighbor = n_info.node

            if not _rel_matches(edge.relationship, rel_set):
                continue

            if neighbor.id == target_id:
                return ShortestPathResult(
                    source_id=source_id,
                    target_id=target_id,
                    length=len(edge_path) + 1,
                    nodes=node_path + [neighbor],
                    edges=edge_path + [edge],
                )

            if neighbor.id not in visited:
                visited.add(neighbor.id)
                queue.append((neighbor.id, node_path + [neighbor], edge_path + [edge]))

    return None


def trace_request_flow(
    graph: DependencyGraph,
    endpoint_or_path: str,
    max_depth: int = 10,
) -> RequestFlowResult:
    """Trace execution flow from an HTTP endpoint or controller to database.

    Follows:
    Endpoint -> Controller -> Service -> Repository -> Database Table
    at both method and type levels, recording evidence and unresolved steps.
    """
    # 1. Resolve starting endpoint or controller
    start_node: GraphNode | None = None

    # Direct match on ID
    start_node = graph.get_node(endpoint_or_path)

    # Match by name or path
    if start_node is None:
        clean_path = endpoint_or_path.strip()
        for n in graph.nodes:
            if n.kind == "endpoint":
                if clean_path in n.id or clean_path in n.name:
                    start_node = n
                    break
            elif n.name == clean_path:
                start_node = n
                break

    if start_node is None:
        return RequestFlowResult(
            endpoint=endpoint_or_path,
            steps=[],
            reaches_database=False,
            database_table=None,
            unresolved_steps=[f"Could not find starting node for '{endpoint_or_path}'"],
        )

    steps: list[RequestFlowStep] = []
    unresolved_calls: list[str] = []
    step_num = 1

    # Record first step
    steps.append(
        RequestFlowStep(
            step_number=step_num,
            node_id=start_node.id,
            node_kind=start_node.kind,
            node_name=start_node.name,
            qualified_name=start_node.qualified_name,
            file_path=start_node.file_path,
            details=start_node.metadata,
        )
    )

    curr_node = start_node
    reaches_database = False
    database_table: str | None = None
    visited_ids: set[str] = {start_node.id}

    # If starting at an endpoint, find the controller or controller method exposing it
    if curr_node.kind == "endpoint":
        incoming = graph.incoming_edges(curr_node.id, RelationshipType.EXPOSES)
        controller_node = None
        # Prefer method over class for precision
        for inc in incoming:
            src = graph.get_node(inc.source_id)
            if src and src.kind == "method":
                controller_node = src
                break
        if not controller_node and incoming:
            src = graph.get_node(incoming[0].source_id)
            if src:
                controller_node = src

        if controller_node:
            step_num += 1
            steps.append(
                RequestFlowStep(
                    step_number=step_num,
                    node_id=controller_node.id,
                    node_kind=controller_node.kind,
                    node_name=controller_node.name,
                    qualified_name=controller_node.qualified_name,
                    file_path=controller_node.file_path,
                    relationship="EXPOSES",
                    target_id=curr_node.id,
                    details=controller_node.metadata,
                )
            )
            curr_node = controller_node
            visited_ids.add(controller_node.id)

    # Now step through CALLS / DEPENDS_ON / QUERIES / REFERENCES
    # using BFS to find a path to a database table
    for _ in range(max_depth):
        if curr_node.kind == "database_table":
            reaches_database = True
            database_table = curr_node.name
            break

        # Check unresolved calls from current node
        for edge in graph.outgoing_edges(curr_node.id, RelationshipType.CALLS):
            if not edge.resolved:
                unresolved_calls.append(edge.target_id.replace("unresolved:", ""))

        # Look for next logical step in: CALLS -> QUERIES -> REFERENCES -> DEPENDS_ON
        next_candidates: list[tuple[GraphNode, GraphEdge]] = []

        # 1. Check CALLS edges (method-level flow)
        for edge in graph.outgoing_edges(curr_node.id, RelationshipType.CALLS):
            if edge.resolved:
                target = graph.get_node(edge.target_id)
                if target and target.id not in visited_ids:
                    next_candidates.append((target, edge))

        # 2. Check QUERIES edges (e.g. Repository -> Table)
        for edge in graph.outgoing_edges(curr_node.id, RelationshipType.QUERIES):
            target = graph.get_node(edge.target_id)
            if target and target.id not in visited_ids:
                next_candidates.append((target, edge))

        # 3. Check REFERENCES edges (e.g. Entity -> Table)
        for edge in graph.outgoing_edges(curr_node.id, RelationshipType.REFERENCES):
            target = graph.get_node(edge.target_id)
            if target and target.id not in visited_ids:
                next_candidates.append((target, edge))

        # 4. Check DEPENDS_ON edges if no call edge matched (type-level flow)
        if not next_candidates:
            for edge in graph.outgoing_edges(curr_node.id, RelationshipType.DEPENDS_ON):
                target = graph.get_node(edge.target_id)
                if target and target.id not in visited_ids:
                    next_candidates.append((target, edge))

        if not next_candidates:
            # If current node is a class/interface, check if its methods lead somewhere
            method_edges: list[GraphEdge] = []
            for n in graph.nodes:
                if n.kind == "method" and curr_node.qualified_name and (
                    n.qualified_name and n.qualified_name.startswith(curr_node.qualified_name)
                ):
                    method_edges.extend(graph.outgoing_edges(n.id))

            for me in method_edges:
                if me.relationship in (RelationshipType.CALLS, RelationshipType.QUERIES):
                    target = graph.get_node(me.target_id)
                    if target and target.id not in visited_ids:
                        next_candidates.append((target, me))

        if not next_candidates and curr_node.kind == "method" and "#" in curr_node.id:
            # Check if owning class/interface queries or references a database table
            type_qname = curr_node.id.split("#")[0].replace("method:", "type:")
            type_node = graph.get_node(type_qname)
            if type_node:
                for edge in graph.outgoing_edges(type_node.id):
                    if edge.relationship in (RelationshipType.QUERIES, RelationshipType.REFERENCES, RelationshipType.DEPENDS_ON):
                        target = graph.get_node(edge.target_id)
                        if target and target.kind == "database_table" and target.id not in visited_ids:
                            next_candidates.append((target, edge))

        if not next_candidates:
            break

        # Prioritize candidates: database_table > repository > service > others
        def _candidate_priority(item: tuple[GraphNode, GraphEdge]) -> int:
            node, _ = item
            if node.kind == "database_table":
                return 0
            if "repository" in node.id.lower() or "Repository" in node.name:
                return 1
            if "service" in node.id.lower() or "Service" in node.name:
                return 2
            if "entity" in node.id.lower() or "Entity" in node.name:
                return 3
            return 4

        next_candidates.sort(key=_candidate_priority)
        best_node, best_edge = next_candidates[0]

        step_num += 1
        rel_str = best_edge.relationship.value if isinstance(best_edge.relationship, Enum) else str(best_edge.relationship)
        steps.append(
            RequestFlowStep(
                step_number=step_num,
                node_id=best_node.id,
                node_kind=best_node.kind,
                node_name=best_node.name,
                qualified_name=best_node.qualified_name,
                file_path=best_node.file_path,
                relationship=rel_str,
                target_id=best_node.id,
                details=best_node.metadata,
                unresolved_calls=list(set(unresolved_calls)),
            )
        )
        visited_ids.add(best_node.id)
        curr_node = best_node

        if curr_node.kind == "database_table":
            reaches_database = True
            database_table = curr_node.name
            break

    return RequestFlowResult(
        endpoint=endpoint_or_path,
        steps=steps,
        reaches_database=reaches_database,
        database_table=database_table,
        unresolved_steps=list(dict.fromkeys(unresolved_calls)),
    )


def impact_traversal(
    graph: DependencyGraph,
    target_symbol: str,
    max_depth: int = 5,
) -> ImpactResult:
    """Perform bounded impact analysis by traversing callers and dependents."""
    target_node: GraphNode | None = graph.get_node(target_symbol)
    if target_node is None:
        # Search by exact name or qualified name
        for n in graph.nodes:
            if n.name == target_symbol or n.qualified_name == target_symbol:
                target_node = n
                break

    if target_node is None:
        # Check Class.method or Class#method patterns (e.g. PaymentService.processPayment)
        clean_sym = target_symbol.replace(".", "#")
        for n in graph.nodes:
            if n.kind == "method":
                if (
                    clean_sym in n.id
                    or n.id.endswith(clean_sym)
                    or (n.qualified_name and (n.qualified_name.endswith(target_symbol) or target_symbol in n.qualified_name))
                ):
                    target_node = n
                    break

    if target_node is None:
        # Fallback to substring matching in ID
        for n in graph.nodes:
            if target_symbol in n.id:
                target_node = n
                break

    if target_node is None:
        return ImpactResult(
            target_id=target_symbol,
            target_name=target_symbol,
            target_kind="unknown",
            max_depth=max_depth,
            affected_nodes=[],
            affected_by_depth={},
            affected_callers=[],
            affected_controllers=[],
            affected_endpoints=[],
            affected_services=[],
            affected_repositories=[],
            affected_tests=[],
        )

    # Traverse incoming edges (callers, dependents, users, testers)
    traversal = bounded_traversal(
        graph,
        start_id=target_node.id,
        max_depth=max_depth,
        direction="incoming",
        relationships=["CALLS", "DEPENDS_ON", "USES", "TESTS", "EXPOSES"],
    )

    affected_nodes = [n for n in traversal.visited_nodes if n.id != target_node.id]
    affected_by_depth: dict[int, list[GraphNode]] = {}
    for n in affected_nodes:
        d = traversal.depth_map.get(n.id, 1)
        affected_by_depth.setdefault(d, []).append(n)

    affected_callers: list[GraphNode] = []
    affected_controllers: list[GraphNode] = []
    affected_endpoints: list[GraphNode] = []
    affected_services: list[GraphNode] = []
    affected_repositories: list[GraphNode] = []
    affected_tests: list[GraphNode] = []

    for node in affected_nodes:
        name_lower = node.name.lower()
        id_lower = node.id.lower()

        if node.kind == "method":
            affected_callers.append(node)
        elif node.kind == "endpoint":
            affected_endpoints.append(node)

        if "controller" in name_lower or "controller" in id_lower:
            if node not in affected_controllers:
                affected_controllers.append(node)
        elif "service" in name_lower or "service" in id_lower:
            if "test" not in name_lower and node not in affected_services:
                affected_services.append(node)
        elif "repository" in name_lower or "repository" in id_lower:
            if node not in affected_repositories:
                affected_repositories.append(node)

        if "test" in name_lower or "test" in id_lower:
            if node not in affected_tests:
                affected_tests.append(node)

    return ImpactResult(
        target_id=target_node.id,
        target_name=target_node.name,
        target_kind=target_node.kind,
        max_depth=max_depth,
        affected_nodes=affected_nodes,
        affected_by_depth=affected_by_depth,
        affected_callers=affected_callers,
        affected_controllers=affected_controllers,
        affected_endpoints=affected_endpoints,
        affected_services=affected_services,
        affected_repositories=affected_repositories,
        affected_tests=affected_tests,
    )


def verify_controller_service_repository(
    graph: DependencyGraph,
) -> list[ArchitectureChain]:
    """Verify Controller -> Service -> Repository -> Database relationships in the graph.

    Finds all architectural chains where:
    - A Controller depends on or calls a Service
    - The Service depends on or calls a Repository
    - The Repository queries a Database Table
    - An Endpoint is exposed by the Controller
    """
    chains: list[ArchitectureChain] = []

    # Find candidate controllers
    controllers = [
        n for n in graph.nodes
        if n.kind == "class" and ("controller" in n.name.lower() or "controller" in n.id.lower())
    ]

    for ctrl in controllers:
        # Check outgoing dependencies from controller to service
        ctrl_deps = graph.outgoing_edges(ctrl.id, RelationshipType.DEPENDS_ON)
        for cd in ctrl_deps:
            service = graph.get_node(cd.target_id)
            if not service or not ("service" in service.name.lower() or "service" in service.id.lower()):
                continue

            # Check outgoing dependencies from service to repository
            svc_deps = graph.outgoing_edges(service.id, RelationshipType.DEPENDS_ON)
            for sd in svc_deps:
                repo = graph.get_node(sd.target_id)
                if not repo or not ("repository" in repo.name.lower() or "repository" in repo.id.lower()):
                    continue

                # Check outgoing queries/dependencies from repository to database table
                table_node = None
                type_edges = [cd, sd]

                repo_queries = graph.outgoing_edges(repo.id, RelationshipType.QUERIES)
                for rq in repo_queries:
                    t = graph.get_node(rq.target_id)
                    if t and t.kind == "database_table":
                        table_node = t
                        type_edges.append(rq)
                        break

                if not table_node:
                    for rd in graph.outgoing_edges(repo.id, RelationshipType.DEPENDS_ON):
                        t = graph.get_node(rd.target_id)
                        if t and t.kind == "database_table":
                            table_node = t
                            type_edges.append(rd)
                            break

                # Find endpoint exposed by controller
                endpoint_node = None
                exp_edges = graph.outgoing_edges(ctrl.id, RelationshipType.EXPOSES)
                if exp_edges:
                    endpoint_node = graph.get_node(exp_edges[0].target_id)

                # Check method-level call chain (Controller method -> Service method -> Repo method)
                call_edges: list[GraphEdge] = []
                for e in graph.edges:
                    if e.relationship == RelationshipType.CALLS and e.resolved:
                        if ctrl.name in e.source_id and service.name in e.target_id:
                            call_edges.append(e)
                        elif service.name in e.source_id and repo.name in e.target_id:
                            call_edges.append(e)

                chains.append(
                    ArchitectureChain(
                        controller_node=ctrl,
                        service_node=service,
                        repository_node=repo,
                        table_node=table_node,
                        endpoint_node=endpoint_node,
                        type_chain_edges=type_edges,
                        call_chain_edges=call_edges,
                        verified=True,
                    )
                )

    return chains
