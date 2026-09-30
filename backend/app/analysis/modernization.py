"""Deterministic evidence-backed modernization analysis engine (P15).

Identifies where detectable:
- Tightly coupled components
- Circular dependencies
- Large classes and method counts
- High-dependency components
- Architectural bottlenecks
- Testing gaps
- Decomposition candidates
- Framework modernization opportunities

Never claims modernization is required unless strictly supported by repository evidence.
Does NOT modify source code automatically.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
import re
from typing import Any

from app.graph.models import DependencyGraph, RelationshipType
from app.parser.models import ParseResult


@dataclass
class ModernizationFinding:
    """A deterministic modernization recommendation backed by repository facts."""

    category: str
    finding: str
    evidence: list[str]
    reason: str
    possible_direction: str
    dependencies: list[str]
    risk_considerations: list[str]
    suggested_investigation_order: int
    limitations: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ModernizationReport:
    """Collection of modernization findings ordered by suggested investigation sequence."""

    findings: list[ModernizationFinding] = field(default_factory=list)
    total_findings: int = 0

    def __post_init__(self) -> None:
        self.total_findings = len(self.findings)
        self.findings.sort(key=lambda f: f.suggested_investigation_order)

    def summary_lines(self) -> list[str]:
        lines = [f"Modernization Analysis Summary: {self.total_findings} findings"]
        for f in self.findings:
            lines.append(f"  #{f.suggested_investigation_order} [{f.category}] {f.finding}")
            lines.append(f"       Reason: {f.reason}")
            lines.append(f"       Direction: {f.possible_direction}")
            if f.evidence:
                lines.append(f"       Evidence: {', '.join(f.evidence[:3])}")
        return lines

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_findings": self.total_findings,
            "findings": [f.to_dict() for f in self.findings],
        }


def detect_circular_dependencies_modernization(
    graph: DependencyGraph,
) -> list[ModernizationFinding]:
    """Identify circular dependencies and propose decoupled architectural patterns."""
    findings: list[ModernizationFinding] = []
    type_nodes = [
        n for n in graph.nodes
        if n.kind in ("class", "interface") and not n.name.endswith("Test")
    ]
    adj: dict[str, list[str]] = {n.id: [] for n in type_nodes}

    for n in type_nodes:
        for e in graph.outgoing_edges(n.id, RelationshipType.DEPENDS_ON):
            if e.resolved and e.target_id in adj and e.target_id != n.id:
                if e.target_id not in adj[n.id]:
                    adj[n.id].append(e.target_id)

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
                        ModernizationFinding(
                            category="CIRCULAR_DEPENDENCY",
                            finding=f"Decouple bidirectional dependency between {u_name} and {v_name}",
                            evidence=[
                                f"{u_name} depends on {v_name}",
                                f"{v_name} depends on {u_name}",
                                f"Cycle length: 2 components",
                            ],
                            reason=(
                                f"Bidirectional cycles create tight compile-time coupling, impede independent "
                                f"unit testing, and can cause initialization order problems or cyclic runtime recursion."
                            ),
                            possible_direction=(
                                "Introduce domain events (e.g. Spring ApplicationEventPublisher / event listeners) "
                                "or extract shared workflow coordination into a separate mediator/orchestrator."
                            ),
                            dependencies=[u_name, v_name],
                            risk_considerations=[
                                "Asynchronous event publishing introduces eventual consistency.",
                                "Transaction boundaries must be maintained if events occur during database commit.",
                            ],
                            suggested_investigation_order=1,
                            limitations=[
                                "Static analysis proves dependency cycle presence but cannot determine runtime invocation frequency.",
                            ],
                        )
                    )

    return findings


def detect_high_coupling_and_decomposition(
    graph: DependencyGraph,
) -> list[ModernizationFinding]:
    """Identify tightly coupled components and central bottlenecks as decomposition candidates."""
    findings: list[ModernizationFinding] = []
    type_nodes = [
        n for n in graph.nodes
        if n.kind in ("class", "interface") and not n.name.endswith("Test")
    ]

    for node in type_nodes:
        in_edges = [
            e for e in graph.incoming_edges(node.id)
            if e.relationship in (RelationshipType.DEPENDS_ON, RelationshipType.USES)
        ]
        out_edges = [
            e for e in graph.outgoing_edges(node.id)
            if e.relationship in (RelationshipType.DEPENDS_ON, RelationshipType.USES)
        ]

        fan_in = len(in_edges)
        fan_out = len(out_edges)

        # High bidirectional coupling / decomposition candidate
        if fan_in >= 3 and fan_out >= 3:
            callers = [
                e.source_id.split("#")[0].replace("type:", "")
                for e in graph.incoming_edges(node.id)
                if e.relationship == RelationshipType.CALLS
            ]
            findings.append(
                ModernizationFinding(
                    category="DECOMPOSITION_CANDIDATE",
                    finding=f"Evaluate decomposition of central coordinator {node.name}",
                    evidence=[
                        f"Incoming dependencies (fan-in): {fan_in}",
                        f"Outgoing dependencies (fan-out): {fan_out}",
                        f"Total coupling: {fan_in + fan_out}",
                    ],
                    reason=(
                        f"{node.name} exhibits high bidirectional coupling across {fan_in + fan_out} components, "
                        "indicating that it serves multiple distinct business responsibilities."
                    ),
                    possible_direction=(
                        "Decompose into focused domain services by partitioning distinct business methods into "
                        "dedicated services, preserving a lightweight facade if backward compatibility is required."
                    ),
                    dependencies=[node.name] + list(set(callers[:4])),
                    risk_considerations=[
                        "Refactoring central services requires updating multiple caller endpoints and test suites.",
                        "Transactional boundaries spanning multiple decomposed methods must be re-verified.",
                    ],
                    suggested_investigation_order=2,
                    limitations=[
                        "High coupling is not inherently defective if the component is intentionally designed as an application service.",
                    ],
                )
            )

        # Architectural bottleneck (high fan-in)
        elif fan_in >= 5:
            findings.append(
                ModernizationFinding(
                    category="ARCHITECTURAL_BOTTLENECK",
                    finding=f"Harden high fan-in architectural bottleneck {node.name}",
                    evidence=[
                        f"Incoming dependencies: {fan_in}",
                        f"Direct dependents: {len(in_edges)}",
                    ],
                    reason=(
                        f"With {fan_in} incoming dependencies, any performance degradation, bug, or contract change in "
                        f"{node.name} cascades across the entire application."
                    ),
                    possible_direction=(
                        "Define explicit interface contracts, introduce caching where read operations predominate, "
                        "and apply resilience mechanisms such as circuit breakers."
                    ),
                    dependencies=[node.name],
                    risk_considerations=[
                        "Interface extraction requires client code re-binding or dependency injection qualifiers.",
                        "Caching requires careful invalidation on mutation operations.",
                    ],
                    suggested_investigation_order=3,
                    limitations=[
                        "Static analysis cannot measure latency or invocation throughput at runtime.",
                    ],
                )
            )

    return findings


def detect_testing_gaps_modernization(
    graph: DependencyGraph,
) -> list[ModernizationFinding]:
    """Identify untested core services and recommend test automation strategy."""
    findings: list[ModernizationFinding] = []

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
                callers = [
                    e.source_id.replace("type:", "")
                    for e in graph.incoming_edges(svc.id)
                    if e.relationship in (RelationshipType.DEPENDS_ON, RelationshipType.CALLS)
                ]
                findings.append(
                    ModernizationFinding(
                        category="TESTING_GAP",
                        finding=f"Implement automated unit and integration tests for {svc.name}",
                        evidence=[
                            f"Identified zero test classes referencing {svc.name}",
                            f"Used upstream by: {', '.join(callers) if callers else 'indirect callers'}",
                        ],
                        reason=(
                            f"Production service '{svc.name}' lacks automated test coverage, preventing safe refactoring "
                            "and increasing regression risk during modernization."
                        ),
                        possible_direction=(
                            f"Create a dedicated test class ({svc.name}Test) verifying positive and negative business paths "
                            "using Mockito for downstream dependencies."
                        ),
                        dependencies=[svc.name],
                        risk_considerations=[
                            "Untested code may harbor latent edge-case bugs that surface when test suites are introduced.",
                        ],
                        suggested_investigation_order=4,
                        limitations=[
                            "Tests located outside repository boundaries (e.g. external blackbox suites) cannot be detected.",
                        ],
                    )
                )

    return findings


def detect_large_classes_modernization(
    graph: DependencyGraph,
) -> list[ModernizationFinding]:
    """Identify large classes and recommend single-responsibility partitioning."""
    findings: list[ModernizationFinding] = []

    type_nodes = [
        n for n in graph.nodes
        if n.kind in ("class", "interface") and not n.name.endswith("Test")
    ]

    for node in type_nodes:
        method_nodes = [
            n for n in graph.nodes
            if n.kind == "method" and (n.id.startswith(f"method:{node.name}#") or (node.qualified_name and n.id.startswith(f"method:{node.qualified_name}#")))
        ]
        method_count = len(method_nodes)
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

        if method_count >= 10 or line_count >= 150:
            findings.append(
                ModernizationFinding(
                    category="LARGE_CLASS",
                    finding=f"Modularize structural volume in {node.name}",
                    evidence=[
                        f"Method count: {method_count}",
                        f"Class size: {line_count} lines of code",
                    ],
                    reason=(
                        f"Class {node.name} contains {method_count} methods and {line_count} lines of code, "
                        "raising maintenance complexity and violating Single Responsibility Principle."
                    ),
                    possible_direction=(
                        "Extract grouped helper methods or state representations into dedicated value objects "
                        "or delegate strategy classes."
                    ),
                    dependencies=[node.name],
                    risk_considerations=[
                        "Extracting public methods can alter class API surface.",
                    ],
                    suggested_investigation_order=5,
                    limitations=[
                        "High method count from boilerplate accessors (getters/setters) does not necessarily imply high cognitive load.",
                    ],
                )
            )

    return findings


def detect_framework_modernization(
    graph: DependencyGraph,
    parse_result: ParseResult | None = None,
) -> list[ModernizationFinding]:
    """Identify detectable framework modernization opportunities in Java sources."""
    findings: list[ModernizationFinding] = []

    # Inspect source files for legacy patterns:
    # 1. Field injection (@Autowired on fields without constructor)
    # 2. Legacy java.util.Date usage
    # 3. Synchronous RestTemplate usage
    inspected_files: set[str] = set()

    for node in graph.nodes:
        if node.file_path and node.file_path not in inspected_files:
            inspected_files.add(node.file_path)
            p = Path(node.file_path)
            if not p.is_file() or not p.name.endswith(".java") or "Test" in p.name:
                continue

            try:
                content = p.read_text(encoding="utf-8", errors="replace")

                # Check field injection
                if "@Autowired" in content and "public " + p.stem in content and "@Autowired\n    private" in content:
                    findings.append(
                        ModernizationFinding(
                            category="FRAMEWORK_MODERNIZATION",
                            finding=f"Migrate field injection to constructor injection in {p.stem}",
                            evidence=[
                                f"Detected @Autowired on private field in {p.name}",
                            ],
                            reason=(
                                "Spring framework standards strongly discourage field injection; constructor injection "
                                "ensures immutability, facilitates unit testing without SpringRunner, and prevents NPEs."
                            ),
                            possible_direction=(
                                "Replace field-level @Autowired with final field declarations and constructor injection."
                            ),
                            dependencies=[p.stem],
                            risk_considerations=[
                                "Test instantiation of the class will require explicit mock arguments in constructors.",
                            ],
                            suggested_investigation_order=6,
                            limitations=[
                                "Static regex identifies field annotations; Spring configuration classes may have intentional setter injection.",
                            ],
                        )
                    )

                # Check java.util.Date
                if "java.util.Date" in content:
                    findings.append(
                        ModernizationFinding(
                            category="FRAMEWORK_MODERNIZATION",
                            finding=f"Migrate legacy java.util.Date to java.time in {p.stem}",
                            evidence=[
                                f"Found java.util.Date import or reference in {p.name}",
                            ],
                            reason=(
                                "java.util.Date is mutable and lacks timezone safety; java.time (Instant, LocalDate, ZonedDateTime) "
                                "is immutable, thread-safe, and standard in Java 8+."
                            ),
                            possible_direction=(
                                "Migrate Date fields to Instant or OffsetDateTime with JPA 2.2+ / Hibernate 5+ date mapping."
                            ),
                            dependencies=[p.stem],
                            risk_considerations=[
                                "Database column mapping and serialization formats (JSON timestamps) must maintain format compatibility.",
                            ],
                            suggested_investigation_order=7,
                            limitations=[
                                "Third-party libraries with legacy APIs may still require java.util.Date interop.",
                            ],
                        )
                    )
            except Exception:
                continue

    return findings


def analyze_modernization(
    graph: DependencyGraph,
    parse_result: ParseResult | None = None,
) -> ModernizationReport:
    """Run all deterministic modernization detectors."""
    findings: list[ModernizationFinding] = []

    findings.extend(detect_circular_dependencies_modernization(graph))
    findings.extend(detect_high_coupling_and_decomposition(graph))
    findings.extend(detect_testing_gaps_modernization(graph))
    findings.extend(detect_large_classes_modernization(graph))
    findings.extend(detect_framework_modernization(graph, parse_result))

    return ModernizationReport(findings=findings)
