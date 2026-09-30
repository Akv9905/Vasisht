"""Dependency graph models (P3)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Literal

NodeKind = Literal[
    "package",
    "class",
    "interface",
    "enum",
    "record",
    "method",
    "field",
    "endpoint",
    "database_table",
    "database_column",
    "file",
    "unknown",
]


class RelationshipType(str, Enum):
    """Types of relationships between graph nodes."""

    CONTAINS = "CONTAINS"
    IMPORTS = "IMPORTS"
    EXTENDS = "EXTENDS"
    IMPLEMENTS = "IMPLEMENTS"
    CALLS = "CALLS"
    USES = "USES"
    EXPOSES = "EXPOSES"
    QUERIES = "QUERIES"
    DEPENDS_ON = "DEPENDS_ON"
    REFERENCES = "REFERENCES"
    TESTS = "TESTS"


@dataclass
class GraphNode:
    """A node in the dependency graph representing a software entity."""

    id: str
    kind: NodeKind | str
    name: str
    qualified_name: str | None = None
    file_path: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GraphEdge:
    """A directed edge in the dependency graph representing a relationship."""

    source_id: str
    target_id: str
    relationship: RelationshipType
    resolved: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        res = asdict(self)
        res["relationship"] = self.relationship.value
        return res


@dataclass
class DependencyGraph:
    """A collection of graph nodes and edges representing code dependencies."""

    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)
    _node_map: dict[str, GraphNode] = field(default_factory=dict, init=False, repr=False)
    _edge_set: set[tuple[str, str, str]] = field(default_factory=set, init=False, repr=False)

    def __post_init__(self) -> None:
        self._node_map = {n.id: n for n in self.nodes}
        self._edge_set = {
            (e.source_id, e.target_id, e.relationship.value if isinstance(e.relationship, Enum) else str(e.relationship))
            for e in self.edges
        }

    def add_node(self, node: GraphNode) -> None:
        """Add a node if it doesn't already exist (by id)."""
        if node.id not in self._node_map:
            self._node_map[node.id] = node
            self.nodes.append(node)
        else:
            # Merge metadata if needed
            existing = self._node_map[node.id]
            if node.metadata:
                existing.metadata.update(node.metadata)
            if not existing.file_path and node.file_path:
                existing.file_path = node.file_path
            if not existing.qualified_name and node.qualified_name:
                existing.qualified_name = node.qualified_name

    def add_edge(self, edge: GraphEdge) -> None:
        """Add an edge if it doesn't already exist."""
        rel_val = edge.relationship.value if isinstance(edge.relationship, Enum) else str(edge.relationship)
        key = (edge.source_id, edge.target_id, rel_val)
        if key not in self._edge_set:
            self._edge_set.add(key)
            self.edges.append(edge)

    def get_node(self, node_id: str) -> GraphNode | None:
        """Get a node by its id."""
        if not self._node_map and self.nodes:
            self._node_map = {n.id: n for n in self.nodes}
        return self._node_map.get(node_id)

    def find_nodes(
        self,
        kind: str | None = None,
        name: str | None = None,
        file_path: str | None = None,
    ) -> list[GraphNode]:
        """Filter nodes by kind, name, or file path."""
        result = self.nodes
        if kind is not None:
            result = [n for n in result if n.kind == kind]
        if name is not None:
            result = [n for n in result if n.name == name]
        if file_path is not None:
            result = [n for n in result if n.file_path == file_path]
        return result

    def outgoing_edges(
        self, node_id: str, relationship: RelationshipType | None = None
    ) -> list[GraphEdge]:
        """Get all edges originating from a node, optionally filtered by relationship."""
        return [
            e
            for e in self.edges
            if e.source_id == node_id
            and (relationship is None or e.relationship == relationship)
        ]

    def incoming_edges(
        self, node_id: str, relationship: RelationshipType | None = None
    ) -> list[GraphEdge]:
        """Get all edges targeting a node, optionally filtered by relationship."""
        return [
            e
            for e in self.edges
            if e.target_id == node_id
            and (relationship is None or e.relationship == relationship)
        ]

    def resolved_edges(self) -> list[GraphEdge]:
        """Edges with target entities resolved in the repository."""
        return [e for e in self.edges if e.resolved]

    def unresolved_edges(self) -> list[GraphEdge]:
        """Edges whose target could not be resolved to a repository declaration."""
        return [e for e in self.edges if not e.resolved]

    def summary(self) -> dict[str, Any]:
        """Return counts by node kind and relationship type."""
        node_counts: dict[str, int] = {}
        for n in self.nodes:
            node_counts[n.kind] = node_counts.get(n.kind, 0) + 1

        rel_counts: dict[str, int] = {}
        for e in self.edges:
            r_name = e.relationship.value if isinstance(e.relationship, Enum) else str(e.relationship)
            rel_counts[r_name] = rel_counts.get(r_name, 0) + 1

        resolved_count = sum(1 for e in self.edges if e.resolved)
        unresolved_count = len(self.edges) - resolved_count

        return {
            "total_nodes": len(self.nodes),
            "total_edges": len(self.edges),
            "resolved_edges": resolved_count,
            "unresolved_edges": unresolved_count,
            "nodes_by_kind": node_counts,
            "edges_by_relationship": rel_counts,
        }

    def summary_lines(self) -> list[str]:
        s = self.summary()
        return [
            f"✓ Dependency graph built ({s['total_nodes']} nodes, {s['total_edges']} edges)",
            f"✓ Relationships resolved ({s['resolved_edges']} resolved, {s['unresolved_edges']} unresolved)",
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary(),
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
        }