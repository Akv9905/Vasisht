"""Deterministic Change Impact Analysis engine (P12).

Traces:
- Direct callers (depth 1)
- Indirect callers (depth > 1)
- Dependent services
- Controllers
- Repositories
- APIs / Endpoints
- Database references / tables
- Tests

Uses bounded graph traversal.
Enforces the enterprise rule:
Use language such as "Potentially affected". Do NOT claim something will
definitely break unless deterministic evidence supports that conclusion.
"""

from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from app.graph.models import DependencyGraph, GraphEdge, GraphNode, RelationshipType
from app.graph.traversal import bounded_traversal

logger = logging.getLogger(__name__)


@dataclass
class ImpactEntity:
    """An entity potentially affected by a change."""

    id: str
    name: str
    kind: str
    file_path: str | None = None
    start_line: int | None = None
    end_line: int | None = None
    depth: int = 1
    relationship: str | None = None
    role: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ImpactAnalysisResult:
    """Complete change-impact analysis result."""

    target: str
    target_kind: str
    target_file: str | None = None
    target_line: int | None = None
    direct_impact: list[dict[str, Any]] = field(default_factory=list)
    indirect_impact: list[dict[str, Any]] = field(default_factory=list)
    affected_apis: list[dict[str, Any]] = field(default_factory=list)
    affected_database_objects: list[dict[str, Any]] = field(default_factory=list)
    affected_tests: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)

    def summary_lines(self) -> list[str]:
        lines = [
            f"Change Impact Analysis for: {self.target} ({self.target_kind})",
            f"  Target File: {self.target_file or 'unknown'}:{self.target_line or '?'}",
            f"  Potentially affected direct entities: {len(self.direct_impact)}",
            f"  Potentially affected indirect entities: {len(self.indirect_impact)}",
            f"  Potentially affected APIs: {len(self.affected_apis)}",
            f"  Potentially affected Database Objects: {len(self.affected_database_objects)}",
            f"  Potentially affected Tests: {len(self.affected_tests)}",
            "",
            "Direct Impact (Depth 1):",
        ]
        if self.direct_impact:
            for item in self.direct_impact:
                lines.append(f"  - [{item.get('kind')}] {item.get('name')} via {item.get('relationship') or 'DEPENDS'}")
        else:
            lines.append("  (None detected)")

        if self.indirect_impact:
            lines.append("")
            lines.append("Indirect Impact (Depth >= 2):")
            for item in self.indirect_impact:
                lines.append(f"  - [Depth {item.get('depth')}] [{item.get('kind')}] {item.get('name')}")

        if self.affected_tests:
            lines.append("")
            lines.append("Affected Tests:")
            for t in self.affected_tests:
                lines.append(f"  - [{t.get('kind')}] {t.get('name')} ({t.get('file_path') or 'test'})")

        if self.affected_database_objects:
            lines.append("")
            lines.append("Affected Database Objects:")
            for db_obj in self.affected_database_objects:
                lines.append(f"  - [{db_obj.get('kind')}] {db_obj.get('name')}")

        lines.append("")
        lines.append("Limitations & Caveats:")
        for lim in self.limitations:
            lines.append(f"  - {lim}")

        return lines

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "target_kind": self.target_kind,
            "target_file": self.target_file,
            "target_line": self.target_line,
            "direct_impact": self.direct_impact,
            "indirect_impact": self.indirect_impact,
            "affected_apis": self.affected_apis,
            "affected_database_objects": self.affected_database_objects,
            "affected_tests": self.affected_tests,
            "evidence": self.evidence,
            "limitations": self.limitations,
        }


def _resolve_target_node(graph: DependencyGraph, target_symbol: str) -> GraphNode | None:
    """Find starting node in graph by ID, name, qualified name, or Class.method."""
    node = graph.get_node(target_symbol)
    if node:
        return node

    # Exact name or qualified name
    for n in graph.nodes:
        if n.name == target_symbol or n.qualified_name == target_symbol:
            return n

    # Class.method or Class#method patterns
    clean_sym = target_symbol.replace(".", "#")
    for n in graph.nodes:
        if n.kind == "method":
            if (
                clean_sym in n.id
                or n.id.endswith(clean_sym)
                or (n.qualified_name and (n.qualified_name.endswith(target_symbol) or target_symbol in n.qualified_name))
            ):
                return n

    # Partial / endswith match
    parts = target_symbol.split(".")
    if len(parts) >= 2:
        cls_name, method_name = parts[-2], parts[-1]
        for n in graph.nodes:
            if n.kind == "method" and n.name == method_name and cls_name in n.id:
                return n

    for n in graph.nodes:
        if target_symbol in n.id or target_symbol in (n.qualified_name or ""):
            return n

    return None


def analyze_change_impact(
    graph: DependencyGraph,
    target_symbol: str,
    max_depth: int = 5,
) -> ImpactAnalysisResult:
    """Perform deterministic bounded change-impact analysis."""
    target_node = _resolve_target_node(graph, target_symbol)
    if target_node is None:
        return ImpactAnalysisResult(
            target=target_symbol,
            target_kind="unknown",
            limitations=[
                f"Target symbol '{target_symbol}' was not found in the analyzed codebase.",
                "No components are known to be affected.",
            ],
        )

    # 1. Upstream Bounded Traversal (incoming edges: callers, dependents, tests)
    upstream = bounded_traversal(
        graph,
        start_id=target_node.id,
        max_depth=max_depth,
        direction="incoming",
        relationships=["CALLS", "DEPENDS_ON", "USES", "TESTS", "EXPOSES"],
    )

    # 2. Downstream Bounded Traversal (outgoing edges: callees, database references)
    downstream = bounded_traversal(
        graph,
        start_id=target_node.id,
        max_depth=max_depth,
        direction="outgoing",
        relationships=["CALLS", "QUERIES", "REFERENCES", "DEPENDS_ON"],
    )

    direct_impact: list[dict[str, Any]] = []
    indirect_impact: list[dict[str, Any]] = []
    affected_apis: list[dict[str, Any]] = []
    affected_database_objects: list[dict[str, Any]] = []
    affected_tests: list[dict[str, Any]] = []
    evidence_list: list[dict[str, Any]] = []
    seen_ids: set[str] = {target_node.id}

    # Find the incoming edge that touches each upstream node for relationship info
    edge_map: dict[str, GraphEdge] = {}
    for edge in upstream.visited_edges:
        if edge.target_id not in edge_map:
            edge_map[edge.target_id] = edge

    for node in upstream.visited_nodes:
        if node.id in seen_ids:
            continue
        seen_ids.add(node.id)

        depth = upstream.depth_map.get(node.id, 1)
        meta = dict(node.metadata or {})
        start_l = meta.get("start_line")
        end_l = meta.get("end_line")
        edge = edge_map.get(node.id)
        rel_val = edge.relationship.value if edge and hasattr(edge.relationship, "value") else (str(edge.relationship) if edge else None)

        item = {
            "id": node.id,
            "name": node.name,
            "kind": node.kind,
            "file_path": node.file_path,
            "start_line": start_l,
            "end_line": end_l,
            "depth": depth,
            "relationship": rel_val,
        }

        if depth == 1:
            direct_impact.append(item)
        else:
            indirect_impact.append(item)

        # Categorize
        name_lower = node.name.lower()
        id_lower = node.id.lower()

        if node.kind == "endpoint" or "api" in id_lower:
            affected_apis.append(item)
        if "test" in name_lower or "test" in id_lower or node.kind == "test_class":
            affected_tests.append(item)

        evidence_list.append({
            "type": "potentially_affected_upstream",
            "symbol": node.name,
            "kind": node.kind,
            "file_path": node.file_path,
            "start_line": start_l,
            "end_line": end_l,
            "depth": depth,
            "relationship": rel_val,
            "details": f"Potentially affected at depth {depth} via incoming {rel_val or 'dependency'}",
        })

    # Downstream database references
    candidate_nodes = list(downstream.visited_nodes)
    for node in list(downstream.visited_nodes):
        if "#" in node.id:
            owning_id = node.id.split("#")[0].replace("method:", "type:")
            owner = graph.get_node(owning_id)
            if owner and owner not in candidate_nodes:
                candidate_nodes.append(owner)

    for node in candidate_nodes:
        if node.id == target_node.id:
            continue
        # Direct table or database reference node
        is_db_node = (
            node.kind in ("database_table", "database_reference", "table")
            or node.id.startswith("table:")
            or (node.kind in ("class", "entity") and "entity" in node.id.lower())
        )
        if is_db_node:
            db_item = {
                "id": node.id,
                "name": node.name,
                "kind": node.kind,
                "file_path": node.file_path,
                "relationship": "QUERIES",
            }
            if db_item not in affected_database_objects:
                affected_database_objects.append(db_item)
                evidence_list.append({
                    "type": "potentially_affected_database",
                    "symbol": node.name,
                    "kind": node.kind,
                    "file_path": node.file_path,
                    "relationship": "QUERIES",
                    "details": f"Target downstream chain queries or references database entity {node.name}",
                })

        # Also inspect outgoing edges for queries/references to tables
        for edge in graph.outgoing_edges(node.id):
            if edge.relationship in ("QUERIES", "REFERENCES", "DEPENDS_ON"):
                dest = graph.get_node(edge.target_id)
                if dest and (
                    dest.kind in ("database_table", "database_reference", "table")
                    or dest.id.startswith("table:")
                ):
                    db_item = {
                        "id": dest.id,
                        "name": dest.name,
                        "kind": dest.kind,
                        "file_path": dest.file_path,
                        "relationship": str(edge.relationship),
                    }
                    if db_item not in affected_database_objects:
                        affected_database_objects.append(db_item)
                        evidence_list.append({
                            "type": "potentially_affected_database",
                            "symbol": dest.name,
                            "kind": dest.kind,
                            "file_path": dest.file_path,
                            "relationship": str(edge.relationship),
                            "details": f"Target downstream chain queries or references database table {dest.name}",
                        })


    meta = dict(target_node.metadata or {})
    limitations = [
        "Identified entities are 'potentially affected' based on compile-time call graphs and dependencies.",
        "Static impact analysis does not guarantee runtime failure; safe changes or non-breaking contracts may not cause breakage.",
        "Dynamic proxies, reflection, and runtime Spring AOP pointcuts are not dynamically resolved.",
    ]

    return ImpactAnalysisResult(
        target=target_node.name,
        target_kind=target_node.kind,
        target_file=target_node.file_path,
        target_line=meta.get("start_line"),
        direct_impact=direct_impact,
        indirect_impact=indirect_impact,
        affected_apis=affected_apis,
        affected_database_objects=affected_database_objects,
        affected_tests=affected_tests,
        evidence=evidence_list,
        limitations=limitations,
    )
