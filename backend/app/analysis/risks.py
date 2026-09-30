"""Deterministic measurable risk analysis engine (P6 & P13).

Calculates technical risk findings based strictly on measurable repository facts:
- Circular dependencies (cycles in type dependencies or method calls)
- High dependency components (fan-in, fan-out, caller and callee count)
- Large classes and method counts (class size lines-of-code and method counts)
- Cyclomatic complexity (branching decision points where source is available)
- Deep inheritance hierarchies (inheritance depth)
- API exposure (exposed endpoints, controller-to-database coupling)
- Database coupling (classes heavily coupled to database entities/tables)
- Testing gaps (production services lacking automated tests)

No arbitrary AI scores. All findings are backed by measurable evidence.
Never claims high dependency is automatically defective software.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
import re
from typing import Any

from app.graph.models import DependencyGraph, RelationshipType
from app.parser.models import ParseResult

_BRANCH_RE = re.compile(r"\b(if|else\s+if|for|while|case|catch)\b|(&&|\|\||\?)")


@dataclass
class RiskFinding:
    """A deterministic technical risk finding backed by repository metrics."""

    finding_type: str
    severity: str  # HIGH, MEDIUM, LOW, INFO
    subject: str
    summary: str
    metrics: dict[str, Any] = field(default_factory=dict)
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RiskReport:
    """Collection of technical risk findings with summary statistics."""

    findings: list[RiskFinding] = field(default_factory=list)
    total_findings: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0

    def __post_init__(self) -> None:
        self.total_findings = len(self.findings)
        self.high_count = sum(1 for f in self.findings if f.severity == "HIGH")
        self.medium_count = sum(1 for f in self.findings if f.severity == "MEDIUM")
        self.low_count = sum(1 for f in self.findings if f.severity in ("LOW", "INFO"))

    def summary_lines(self) -> list[str]:
        lines = [
            f"Risk Analysis Summary: {self.total_findings} findings "
            f"({self.high_count} HIGH, {self.medium_count} MEDIUM, {self.low_count} LOW)"
        ]
        for f in self.findings:
            lines.append(f"  [{f.severity}] {f.finding_type}: {f.subject}")
            lines.append(f"       {f.summary}")
            if f.evidence:
                for ev in f.evidence[:4]:
                    lines.append(f"       - {ev}")
        return lines

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_findings": self.total_findings,
            "high_count": self.high_count,
            "medium_count": self.medium_count,
            "low_count": self.low_count,
            "findings": [f.to_dict() for f in self.findings],
        }


def detect_circular_dependencies(graph: DependencyGraph) -> list[RiskFinding]:
    """Detect circular dependency cycles between classes/interfaces."""
    findings: list[RiskFinding] = []

    type_nodes = [
        n for n in graph.nodes
        if n.kind in ("class", "interface") and not n.name.endswith("Test")
    ]
    adj: dict[str, list[str]] = {n.id: [] for n in type_nodes}

    for n in type_nodes:
        out_edges = graph.outgoing_edges(n.id, RelationshipType.DEPENDS_ON)
        for e in out_edges:
            if e.resolved and e.target_id in adj and e.target_id != n.id:
                if e.target_id not in adj[n.id]:
                    adj[n.id].append(e.target_id)

    # Also include method-level call cycles mapped to types
    for e in graph.edges:
        if e.relationship == RelationshipType.CALLS and e.resolved:
            src_type_id = e.source_id.split("#")[0].replace("method:", "type:")
            tgt_type_id = e.target_id.split("#")[0].replace("method:", "type:")
            if src_type_id in adj and tgt_type_id in adj and src_type_id != tgt_type_id:
                if tgt_type_id not in adj[src_type_id]:
                    adj[src_type_id].append(tgt_type_id)

    # Detect cycles of length 2
    found_cycles: set[frozenset[str]] = set()

    for u in adj:
        for v in adj[u]:
            if u in adj.get(v, []):
                cycle_key = frozenset([u, v])
                if cycle_key not in found_cycles:
                    found_cycles.add(cycle_key)
                    u_node = graph.get_node(u)
                    v_node = graph.get_node(v)
                    u_name = u_node.name if u_node else u
                    v_name = v_node.name if v_node else v

                    findings.append(
                        RiskFinding(
                            finding_type="CIRCULAR_DEPENDENCY",
                            severity="HIGH",
                            subject=f"{u_name} <-> {v_name}",
                            summary=f"Bidirectional circular dependency detected between {u_name} and {v_name}.",
                            metrics={"cycle_length": 2, "nodes": [u_name, v_name]},
                            evidence=[
                                f"{u_name} depends on or calls {v_name}",
                                f"{v_name} depends on or calls {u_name}",
                            ],
                        )
                    )

    return findings


def detect_high_coupling(graph: DependencyGraph) -> list[RiskFinding]:
    """Identify components with high fan-in, fan-out, caller and callee coupling (P13)."""
    findings: list[RiskFinding] = []

    type_nodes = [
        n for n in graph.nodes
        if n.kind in ("class", "interface") and not n.name.endswith("Test")
    ]

    for node in type_nodes:
        # Incoming dependencies (fan-in)
        in_edges = [
            e for e in graph.incoming_edges(node.id)
            if e.relationship in (RelationshipType.DEPENDS_ON, RelationshipType.USES)
        ]
        # Outgoing dependencies (fan-out)
        out_edges = [
            e for e in graph.outgoing_edges(node.id)
            if e.relationship in (RelationshipType.DEPENDS_ON, RelationshipType.USES)
        ]

        fan_in = len(in_edges)
        fan_out = len(out_edges)

        # Callers: methods outside this type calling methods in this type
        callers_set: set[str] = set()
        callees_set: set[str] = set()

        for edge in graph.edges:
            if edge.relationship == RelationshipType.CALLS and edge.resolved:
                src_type = edge.source_id.split("#")[0].replace("method:", "type:")
                tgt_type = edge.target_id.split("#")[0].replace("method:", "type:")

                if tgt_type == node.id and src_type != node.id:
                    callers_set.add(edge.source_id)
                elif src_type == node.id and tgt_type != node.id:
                    callees_set.add(edge.target_id)

        caller_count = len(callers_set)
        callee_count = len(callees_set)
        total_dependencies = fan_in + fan_out

        # Thresholds: fan-in >= 3 or fan-out >= 3 or caller_count >= 2 or callee_count >= 2
        is_high_dep = (fan_in >= 3 and fan_out >= 3) or fan_out >= 4 or (fan_in + fan_out >= 5) or (caller_count + callee_count >= 4)
        if not is_high_dep and (fan_in >= 2 or fan_out >= 2 or caller_count >= 2):
            is_high_dep = True

        if is_high_dep:
            severity = "HIGH" if (fan_in + fan_out >= 6 or caller_count + callee_count >= 6) else "MEDIUM"
            summary_msg = (
                f"{node.name} exhibits high structural dependency "
                f"({fan_in} incoming, {fan_out} outgoing dependencies, {caller_count} callers, {callee_count} callees). "
                "Note: High dependency reflects architectural orchestration or central coordination responsibility; "
                "it does not automatically denote defective software."
            )
            metrics_dict = {
                "incoming_dependencies": fan_in,
                "outgoing_dependencies": fan_out,
                "callers": caller_count,
                "callees": callee_count,
                "dependency_count": total_dependencies,
                "fan_in": fan_in,
                "fan_out": fan_out,
            }
            evidence_items = [
                f"incoming dependencies: {fan_in}",
                f"outgoing dependencies: {fan_out}",
                f"callers: {caller_count}",
                f"callees: {callee_count}",
                f"dependency count: {total_dependencies}",
            ]
            if node.file_path:
                evidence_items.append(f"file: {node.file_path}")

            findings.append(
                RiskFinding(
                    finding_type="HIGH_DEPENDENCY_COMPONENT",
                    severity=severity,
                    subject=node.name,
                    summary=summary_msg,
                    metrics=metrics_dict,
                    evidence=evidence_items,
                )
            )

            # Preserve backward-compatible HIGH_COUPLING / HIGH_FAN_OUT finding types if matching
            if fan_in >= 3 and fan_out >= 3:
                findings.append(
                    RiskFinding(
                        finding_type="HIGH_COUPLING",
                        severity=severity,
                        subject=node.name,
                        summary=f"{node.name} exhibits high bidirectional coupling ({fan_in} incoming, {fan_out} outgoing dependencies).",
                        metrics=metrics_dict,
                        evidence=evidence_items,
                    )
                )
            elif fan_out >= 4:
                findings.append(
                    RiskFinding(
                        finding_type="HIGH_FAN_OUT",
                        severity="MEDIUM",
                        subject=node.name,
                        summary=f"{node.name} has high fan-out coupling ({fan_out} outgoing dependencies).",
                        metrics=metrics_dict,
                        evidence=evidence_items,
                    )
                )

    return findings


def detect_class_size_and_methods(
    graph: DependencyGraph,
    parse_result: ParseResult | None = None,
) -> list[RiskFinding]:
    """Identify large classes and high method count components."""
    findings: list[RiskFinding] = []

    type_nodes = [
        n for n in graph.nodes
        if n.kind in ("class", "interface") and not n.name.endswith("Test")
    ]

    for node in type_nodes:
        # Calculate method count from graph or parse_result
        method_count = 0
        method_nodes = [
            n for n in graph.nodes
            if n.kind == "method" and (n.id.startswith(f"method:{node.name}#") or (node.qualified_name and n.id.startswith(f"method:{node.qualified_name}#")))
        ]
        method_count = len(method_nodes)

        # Calculate class size (lines of code)
        meta = dict(node.metadata or {})
        start_l = meta.get("start_line")
        end_l = meta.get("end_line")
        line_count = 0
        if start_l and end_l:
            line_count = max(1, end_l - start_l + 1)
        elif node.file_path:
            p = Path(node.file_path)
            if p.is_file():
                try:
                    line_count = len(p.read_text(encoding="utf-8", errors="replace").splitlines())
                except Exception:
                    line_count = 0

        if method_count >= 8 or line_count >= 100:
            severity = "HIGH" if (method_count >= 15 or line_count >= 200) else "MEDIUM"
            evidence_items = [
                f"method count: {method_count}",
                f"class size: {line_count} lines of code",
            ]
            if node.file_path:
                evidence_items.append(f"file: {node.file_path}")

            findings.append(
                RiskFinding(
                    finding_type="LARGE_CLASS",
                    severity=severity,
                    subject=node.name,
                    summary=f"{node.name} has high structural volume ({method_count} methods, {line_count} lines of code).",
                    metrics={"method_count": method_count, "line_count": line_count, "class_size": line_count},
                    evidence=evidence_items,
                )
            )

    return findings


def detect_cyclomatic_complexity(
    graph: DependencyGraph,
    parse_result: ParseResult | None = None,
) -> list[RiskFinding]:
    """Identify methods with elevated cyclomatic complexity where source code is available."""
    findings: list[RiskFinding] = []

    method_nodes = [n for n in graph.nodes if n.kind == "method" and not n.name.startswith("test")]

    for m_node in method_nodes:
        meta = dict(m_node.metadata or {})
        start_l = meta.get("start_line")
        end_l = meta.get("end_line")
        file_path = m_node.file_path

        if not file_path or not start_l or not end_l:
            continue

        p = Path(file_path)
        if not p.is_file():
            continue

        try:
            lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
            method_lines = lines[max(0, start_l - 1):end_l]
            code = "\n".join(method_lines)
            code = re.sub(r"//.*", "", code)
            code = re.sub(r"/\*[\s\S]*?\*/", "", code)
            branches = len(_BRANCH_RE.findall(code))
            complexity = 1 + branches

            if complexity >= 6:
                severity = "HIGH" if complexity >= 12 else "MEDIUM"
                findings.append(
                    RiskFinding(
                        finding_type="HIGH_CYCLOMATIC_COMPLEXITY",
                        severity=severity,
                        subject=m_node.name,
                        summary=f"Method '{m_node.name}' has elevated cyclomatic complexity ({complexity} decision paths).",
                        metrics={"cyclomatic_complexity": complexity, "start_line": start_l, "end_line": end_l},
                        evidence=[
                            f"cyclomatic complexity: {complexity}",
                            f"method: {m_node.name}",
                            f"file: {file_path}:{start_l}-{end_l}",
                        ],
                    )
                )
        except Exception:
            continue

    return findings


def detect_inheritance_depth(
    graph: DependencyGraph,
    parse_result: ParseResult | None = None,
) -> list[RiskFinding]:
    """Identify classes with deep inheritance hierarchies."""
    findings: list[RiskFinding] = []

    type_nodes = [
        n for n in graph.nodes
        if n.kind in ("class", "interface") and not n.name.endswith("Test")
    ]

    for node in type_nodes:
        # Trace outgoing EXTENDS / IMPLEMENTS
        depth = 0
        current_id = node.id
        visited: set[str] = {current_id}
        hierarchy: list[str] = [node.name]

        while True:
            parent_edges = [
                e for e in graph.outgoing_edges(current_id)
                if e.relationship in (RelationshipType.EXTENDS, RelationshipType.IMPLEMENTS) and e.resolved
            ]
            if not parent_edges:
                break
            next_parent = parent_edges[0].target_id
            if next_parent in visited:
                break
            visited.add(next_parent)
            parent_node = graph.get_node(next_parent)
            p_name = parent_node.name if parent_node else next_parent
            hierarchy.append(p_name)
            depth += 1
            current_id = next_parent

        if depth >= 2:
            findings.append(
                RiskFinding(
                    finding_type="DEEP_INHERITANCE",
                    severity="LOW",
                    subject=node.name,
                    summary=f"{node.name} participates in a deep inheritance hierarchy of depth {depth}.",
                    metrics={"inheritance_depth": depth, "hierarchy": hierarchy},
                    evidence=[
                        f"inheritance depth: {depth}",
                        f"hierarchy: {' -> '.join(hierarchy)}",
                    ],
                )
            )

    return findings


def detect_api_exposure(graph: DependencyGraph) -> list[RiskFinding]:
    """Identify API endpoints directly coupled to database or lacking service abstraction."""
    findings: list[RiskFinding] = []

    controllers = [
        n for n in graph.nodes
        if n.kind == "class" and ("controller" in n.name.lower() or "controller" in n.id.lower())
    ]

    for ctrl in controllers:
        endpoints = [
            e for e in graph.outgoing_edges(ctrl.id, RelationshipType.EXPOSES)
        ]
        # Check direct database queries/references bypassing service
        db_bypass = [
            e for e in graph.outgoing_edges(ctrl.id)
            if e.relationship in (RelationshipType.QUERIES, RelationshipType.REFERENCES)
        ]

        if db_bypass:
            tables = [e.target_id.replace("table:", "") for e in db_bypass]
            findings.append(
                RiskFinding(
                    finding_type="API_DATABASE_BYPASS",
                    severity="HIGH",
                    subject=ctrl.name,
                    summary=f"Controller '{ctrl.name}' directly queries database tables without service layer encapsulation.",
                    metrics={"direct_db_bypass": True, "bypassed_tables": tables},
                    evidence=[
                        f"controller: {ctrl.name}",
                        f"direct database queries: {', '.join(tables)}",
                    ],
                )
            )

    return findings


def detect_database_coupling(graph: DependencyGraph) -> list[RiskFinding]:
    """Identify components with direct database table coupling."""
    findings: list[RiskFinding] = []

    for node in graph.nodes:
        if node.kind in ("class", "interface"):
            db_edges = [
                e for e in graph.outgoing_edges(node.id)
                if e.relationship in (RelationshipType.QUERIES, RelationshipType.REFERENCES)
            ]
            if len(db_edges) >= 2:
                tables = [e.target_id.replace("table:", "") for e in db_edges]
                findings.append(
                    RiskFinding(
                        finding_type="DATABASE_COUPLING",
                        severity="MEDIUM",
                        subject=node.name,
                        summary=f"{node.name} directly accesses or references {len(db_edges)} database elements.",
                        metrics={"database_references": len(db_edges), "targets": tables},
                        evidence=[
                            f"database coupling count: {len(db_edges)}",
                            f"references/queries: {', '.join(tables)}",
                        ],
                    )
                )

    return findings


def detect_testing_gaps(graph: DependencyGraph) -> list[RiskFinding]:
    """Identify core business services without matching test classes."""
    findings: list[RiskFinding] = []

    services = [
        n for n in graph.nodes
        if n.kind == "class"
        and n.file_path is not None
        and n.name != "Service"
        and ("service" in n.name.lower() or "service" in n.id.lower())
        and not n.name.endswith("Test")
    ]

    for svc in services:
        test_edges = [e for e in graph.incoming_edges(svc.id, RelationshipType.TESTS)]
        if not test_edges:
            all_in = graph.incoming_edges(svc.id)
            tested = any("test" in e.source_id.lower() for e in all_in)
            if not tested:
                findings.append(
                    RiskFinding(
                        finding_type="TESTING_GAP",
                        severity="MEDIUM",
                        subject=svc.name,
                        summary=f"Service '{svc.name}' has no identifiable automated test coverage.",
                        metrics={"has_tests": False},
                        evidence=[
                            f"test presence: False",
                            f"no test class references or tests {svc.name}",
                        ],
                    )
                )

    return findings


def analyze_risks(
    parse_result: ParseResult | None = None,
    graph: DependencyGraph | None = None,
) -> RiskReport:
    """Run all deterministic risk analysis detectors."""
    findings: list[RiskFinding] = []

    if graph is not None:
        findings.extend(detect_circular_dependencies(graph))
        findings.extend(detect_high_coupling(graph))
        findings.extend(detect_database_coupling(graph))
        findings.extend(detect_testing_gaps(graph))
        findings.extend(detect_class_size_and_methods(graph, parse_result))
        findings.extend(detect_cyclomatic_complexity(graph, parse_result))
        findings.extend(detect_inheritance_depth(graph, parse_result))
        findings.extend(detect_api_exposure(graph))

    # Sort findings by severity (HIGH > MEDIUM > LOW > INFO)
    severity_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "INFO": 3}
    findings.sort(key=lambda f: severity_order.get(f.severity, 4))

    return RiskReport(findings=findings)
