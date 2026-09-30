"""Deterministic report generation engine (P6 & P16).

Generates comprehensive 11-section reports in Markdown or JSON format:
1. Executive summary
2. Repository inventory
3. Architecture
4. Dependencies
5. Request flows
6. Risk indicators
7. Impact analysis
8. Modernization findings
9. Test observations
10. Evidence
11. Limitations

Never hardcodes repository statistics. All metrics reflect actual static analysis data.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any

from app.analysis.architecture import build_architecture_view
from app.analysis.impact import analyze_change_impact
from app.analysis.modernization import analyze_modernization
from app.analysis.risks import RiskReport, analyze_risks
from app.graph.models import DependencyGraph, RelationshipType
from app.graph.traversal import (
    ArchitectureChain,
    RequestFlowResult,
    trace_request_flow,
    verify_controller_service_repository,
)
from app.ingestion.scanner import ScanResult
from app.parser.models import ParseResult


def generate_markdown_report(
    scan: ScanResult,
    parse_result: ParseResult | None,
    graph: DependencyGraph | None,
) -> str:
    """Generate an 11-section Markdown report."""
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines: list[str] = [
        "# Software Intelligence & Architecture Report",
        f"*Generated on: {now_str}*",
        f"*Repository: {scan.source}*",
        "",
        "---",
        "",
        "## 1. Executive Summary",
        "",
    ]

    total_files = scan.total_files
    java_files = len(scan.java_files)
    pkg_count = len(parse_result.packages) if parse_result else 0
    cls_count = len(parse_result.classes) if parse_result else 0
    ep_count = len(parse_result.endpoints) if parse_result else 0
    node_count = len(graph.nodes) if graph else 0
    edge_count = len(graph.edges) if graph else 0

    risk_report = analyze_risks(parse_result, graph)
    mod_report = analyze_modernization(graph, parse_result) if graph else None

    lines.extend([
        f"The analyzed repository contains **{total_files}** total files, including **{java_files}** Java source files across **{pkg_count}** packages.",
        f"Architectural extraction discovered **{cls_count}** classes, **{ep_count}** REST API endpoints, and constructed a knowledge graph of **{node_count}** nodes and **{edge_count}** relationships.",
        f"Technical risk assessment identified **{risk_report.total_findings}** measurable findings ({risk_report.high_count} HIGH, {risk_report.medium_count} MEDIUM, {risk_report.low_count} LOW).",
        f"Modernization analysis identified **{mod_report.total_findings if mod_report else 0}** evidence-backed candidates for architectural improvement.",
        "",
        "## 2. Repository Inventory",
        "",
        f"- **Source path:** `{scan.source}`",
        f"- **From archive (ZIP):** `{scan.from_zip}`",
        f"- **Total files:** {scan.total_files}",
        f"- **Java files:** {len(scan.java_files)}",
        f"- **Configuration files:** {len(scan.configuration_files)}",
        f"- **SQL files:** {len(scan.sql_files)}",
        f"- **Documentation files:** {len(scan.documentation_files)}",
        f"- **Ignored directories:** {', '.join(sorted(scan.ignored_dirs)) if scan.ignored_dirs else 'none'}",
        "",
        "## 3. Architecture",
        "",
    ])

    chains: list[ArchitectureChain] = []
    if graph:
        chains = verify_controller_service_repository(graph)

    if chains:
        lines.append("### Verified Controller -> Service -> Repository Chains")
        lines.append("")
        for i, c in enumerate(chains, start=1):
            ep_str = f"`{c.endpoint_node.name}` -> " if c.endpoint_node else ""
            table_str = f" -> `{c.table_node.name}`" if c.table_node else ""
            lines.append(f"{i}. {ep_str}**{c.controller_node.name}** -> **{c.service_node.name}** -> **{c.repository_node.name}**{table_str}")
        lines.append("")
    else:
        lines.append("No complete 3-tier Controller -> Service -> Repository chains identified.\n")

    lines.extend([
        "## 4. Dependencies",
        "",
    ])
    if graph:
        s = graph.summary()
        lines.extend([
            f"- **Total Nodes:** {s['total_nodes']}",
            f"- **Total Relationships:** {s['total_edges']} ({s['resolved_edges']} resolved, {s['unresolved_edges']} unresolved)",
            "",
            "#### Edge Distribution by Relationship Type:",
            "",
        ])
        for rel, count in sorted(s["edges_by_relationship"].items(), key=lambda x: -x[1]):
            lines.append(f"- `{rel}`: {count}")
        lines.append("")
    else:
        lines.append("Dependency graph not available.\n")

    lines.extend([
        "## 5. Request Flows",
        "",
    ])
    if graph and parse_result and parse_result.endpoints:
        for ep in parse_result.endpoints:
            flow: RequestFlowResult = trace_request_flow(graph, ep.path)
            lines.append(f"### Flow: `{ep.http_method} {ep.path}`")
            for step in flow.steps:
                rel = f" --[{step.relationship}]--> " if step.relationship else ""
                lines.append(f"- **Step {step.step_number}:** `[{step.node_kind}]` {step.node_name}{rel}")
            if flow.reaches_database:
                lines.append(f"- **Database Destination:** Reaches table `{flow.database_table}`")
            if flow.unresolved_steps:
                lines.append(f"- **Unresolved calls:** {', '.join(flow.unresolved_steps)}")
            lines.append("")
    else:
        lines.append("No active REST endpoints discovered for flow tracing.\n")

    lines.extend([
        "## 6. Risks",
        "",
    ])
    if risk_report.findings:
        for f in risk_report.findings:
            lines.append(f"### [{f.severity}] {f.finding_type}: {f.subject}")
            lines.append(f"{f.summary}")
            if f.evidence:
                lines.append("**Evidence:**")
                for ev in f.evidence:
                    lines.append(f"- {ev}")
            lines.append("")
    else:
        lines.append("No high or medium technical risks identified.\n")

    lines.extend([
        "## 7. Change Impact Analysis",
        "",
        "Components identified with highest blast radius in the repository:",
        "",
    ])
    if graph:
        type_nodes = [n for n in graph.nodes if n.kind in ("class", "interface") and not n.name.endswith("Test")]
        ranked_nodes = sorted(
            type_nodes,
            key=lambda n: len(graph.incoming_edges(n.id)),
            reverse=True,
        )
        for n in ranked_nodes[:5]:
            incoming_count = len(graph.incoming_edges(n.id))
            impact_res = analyze_change_impact(graph, n.name, max_depth=3)
            lines.append(
                f"- **{n.name}** (`{n.kind}`): {incoming_count} incoming dependents. "
                f"Potentially affects {len(impact_res.direct_impact)} direct, {len(impact_res.indirect_impact)} indirect components."
            )
        lines.append("")
    else:
        lines.append("Impact data not available.\n")

    lines.extend([
        "## 8. Modernization Opportunities",
        "",
    ])
    if mod_report and mod_report.findings:
        for f in mod_report.findings:
            lines.append(f"### #{f.suggested_investigation_order} [{f.category}] {f.finding}")
            lines.append(f"- **Reason:** {f.reason}")
            lines.append(f"- **Direction:** {f.possible_direction}")
            lines.append(f"- **Dependencies:** {', '.join(f.dependencies)}")
            lines.append(f"- **Evidence:** {'; '.join(f.evidence)}")
            if f.risk_considerations:
                lines.append(f"- **Risks/Considerations:** {'; '.join(f.risk_considerations)}")
            lines.append("")
    else:
        lines.append("No modernization candidates identified based on current static metrics.\n")

    lines.extend([
        "## 9. Test Observations",
        "",
    ])
    if parse_result:
        test_files = [f for f in parse_result.files if "test" in f.file_path.lower()]
        test_types = [t.name for f in test_files for t in f.types]
        lines.extend([
            f"- **Test Files Discovered:** {len(test_files)}",
            f"- **Test Classes:** {', '.join(test_types) if test_types else 'None'}",
            f"- **Production Services with Gaps:** {', '.join(f.subject for f in risk_report.findings if f.finding_type == 'TESTING_GAP') or 'None'}",
            "",
        ])

    lines.extend([
        "## 10. Evidence",
        "",
        "All findings in this report are deterministically extracted from source code ASTs and verified dependency graphs.",
        "No LLM hallucination or synthetic relationships have been introduced.",
        "",
        "Key Grounding Evidence:",
        f"- Parsed {java_files} Java compilation units using exact AST node spans.",
        f"- Verified {len(chains)} full 3-tier Controller -> Service -> Repository -> Database chains.",
        f"- Calculated coupling metrics from {node_count} nodes and {edge_count} directed edges.",
        "",
        "## 11. Limitations",
        "",
        "- Dynamic runtime reflection, Spring XML wiring, and bytecode manipulation are not dynamically resolved.",
        "- Method invocation resolution is limited to static compile-time symbol resolution.",
        "- External libraries and vendor dependencies outside the repository source are marked as unresolved.",
        "- Change impact analysis identifies 'potentially affected' components; static analysis does not guarantee runtime failure.",
        "",
    ])

    return "\n".join(lines)


def generate_json_report(
    scan: ScanResult,
    parse_result: ParseResult | None,
    graph: DependencyGraph | None,
) -> str:
    """Generate a structured JSON report covering all 11 required sections."""
    risk_report = analyze_risks(parse_result, graph)
    mod_report = analyze_modernization(graph, parse_result) if graph else None
    chains = verify_controller_service_repository(graph) if graph else []

    flows = []
    if graph and parse_result:
        for ep in parse_result.endpoints:
            flows.append(trace_request_flow(graph, ep.path).to_dict())

    arch_view = build_architecture_view(graph, parse_result) if graph else None

    # Calculate blast radius for top components
    impacts = []
    if graph:
        type_nodes = [n for n in graph.nodes if n.kind in ("class", "interface") and not n.name.endswith("Test")]
        ranked_nodes = sorted(
            type_nodes,
            key=lambda n: len(graph.incoming_edges(n.id)),
            reverse=True,
        )
        for n in ranked_nodes[:4]:
            imp = analyze_change_impact(graph, n.name, max_depth=3)
            impacts.append(imp.to_dict())

    test_files = [f.file_path for f in parse_result.files if "test" in f.file_path.lower()] if parse_result else []

    data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        # 1. Executive Summary
        "executive_summary": {
            "total_files": scan.total_files,
            "java_files": len(scan.java_files),
            "packages_count": len(parse_result.packages) if parse_result else 0,
            "classes_count": len(parse_result.classes) if parse_result else 0,
            "endpoints_count": len(parse_result.endpoints) if parse_result else 0,
            "total_nodes": len(graph.nodes) if graph else 0,
            "total_relationships": len(graph.edges) if graph else 0,
            "risk_findings_count": risk_report.total_findings,
            "modernization_candidates_count": mod_report.total_findings if mod_report else 0,
        },
        # 2. Repository Inventory
        "repository_inventory": {
            "source": scan.source,
            "from_zip": scan.from_zip,
            "total_files": scan.total_files,
            "java_files": len(scan.java_files),
            "config_files": len(scan.configuration_files),
            "sql_files": len(scan.sql_files),
            "doc_files": len(scan.documentation_files),
            "ignored_dirs": sorted(list(scan.ignored_dirs)),
        },
        # 3. Architecture
        "architecture": arch_view.to_dict() if arch_view else {
            "verified_chains": [c.to_dict() for c in chains],
        },
        # 4. Dependencies
        "dependencies": {
            "graph_summary": graph.summary() if graph else None,
        },
        # 5. Request Flows
        "request_flows": flows,
        # 6. Risk Indicators
        "risk_indicators": risk_report.to_dict(),
        # 7. Impact Analysis
        "impact_analysis": impacts,
        # 8. Modernization Findings
        "modernization_findings": mod_report.to_dict() if mod_report else {"total_findings": 0, "findings": []},
        # 9. Test Observations
        "test_observations": {
            "test_files_count": len(test_files),
            "test_files": test_files,
            "testing_gaps": [f.subject for f in risk_report.findings if f.finding_type == "TESTING_GAP"],
        },
        # 10. Evidence
        "evidence": [
            f"Parsed {len(scan.java_files)} Java compilation units.",
            f"Extracted {len(chains)} verified Controller -> Service -> Repository chains.",
            f"Constructed knowledge graph with {len(graph.nodes) if graph else 0} nodes and {len(graph.edges) if graph else 0} edges.",
        ],
        # 11. Limitations
        "limitations": [
            "Static AST and call graph analysis only; dynamic runtime proxies and reflection not resolved.",
            "External vendor packages outside the repository source are marked as unresolved.",
            "Change impact analysis identifies potentially affected entities rather than guaranteed runtime breakages.",
        ],
        # Backward-compatible fields
        "inventory": {
            "source": scan.source,
            "total_files": scan.total_files,
            "java_files": len(scan.java_files),
            "config_files": len(scan.configuration_files),
            "sql_files": len(scan.sql_files),
            "doc_files": len(scan.documentation_files),
        },
        "graph_summary": graph.summary() if graph else None,
        "risks": risk_report.to_dict(),
    }
    return json.dumps(data, indent=2)
