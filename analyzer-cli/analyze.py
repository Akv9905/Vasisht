#!/usr/bin/env python3
"""
Enterprise AI analyzer CLI (P0–P6).

Supports 12 commands:
  analyze           Scan, parse, extract graph, verify architecture, and analyze risks (default)
  inspect           High-level structural and architectural inspection of the repository
  list-classes      List discovered packages, classes, interfaces, records, and enums
  list-methods      List all methods with signatures, return types, and annotations
  show-class        Detailed inspection of a specific class (fields, methods, dependencies)
  show-dependencies Show incoming and outgoing dependencies of a symbol or overall statistics
  show-graph        Display dependency graph topology, node kinds, and relationship counts
  trace-request     Trace request flow from HTTP endpoint/controller down to database table
  impact            Run change-impact analysis for a class or method symbol
  risks             Run deterministic measurable technical risk analysis
  ask               Ask questions about the repository answered using deterministic evidence
  report            Generate a comprehensive 11-section report in Markdown or JSON

Usage:
  python analyzer-cli/analyze.py <path> [command] [args...]
  python analyzer-cli/analyze.py <command> <path> [args...]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow importing the backend package without installation.
ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.analysis import analyze_risks, answer_question  # noqa: E402
from app.database import session_scope  # noqa: E402
from app.graph.extractor import extract_dependencies  # noqa: E402
from app.graph.models import RelationshipType  # noqa: E402
from app.graph.traversal import (  # noqa: E402
    get_direct_neighbors,
    impact_traversal,
    trace_request_flow,
    verify_controller_service_repository,
)
from app.ingestion.scanner import scan_path  # noqa: E402
from app.parser import parse_java_files  # noqa: E402
from app.persistence import persist_analysis  # noqa: E402
from app.reports import generate_json_report, generate_markdown_report  # noqa: E402

COMMANDS = {
    "analyze",
    "inspect",
    "list-classes",
    "list-methods",
    "show-class",
    "show-dependencies",
    "show-graph",
    "trace-request",
    "impact",
    "risks",
    "ask",
    "report",
    "architecture",
}


def _configure_stdout() -> None:
    """Prefer UTF-8 on Windows consoles so checkmark output does not crash."""
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if callable(reconfigure):
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass


def _safe_print(text: str) -> None:
    try:
        print(text)
    except UnicodeEncodeError:
        print(
            text.replace("✓", "[OK]")
            .encode(sys.stdout.encoding or "ascii", errors="replace")
            .decode(sys.stdout.encoding or "ascii", errors="replace")
        )


def _normalize_cli_args(raw_argv: list[str]) -> tuple[str, str, list[str]]:
    """Normalize CLI arguments to (command, path, remaining_args).

    Supports:
      python analyze.py ./repo
      python analyze.py ./repo ask "How does /api/payment reach the database?"
      python analyze.py ./repo impact PaymentService.processPayment
      python analyze.py ask ./repo "How does /api/payment reach the database?"
    """
    if not raw_argv:
        return "analyze", ".", []

    first = raw_argv[0]

    # Pattern: python analyze.py <command> <path> [args...]
    if first in COMMANDS:
        cmd = first
        path = raw_argv[1] if len(raw_argv) > 1 and not raw_argv[1].startswith("-") else "."
        rem = raw_argv[2:] if len(raw_argv) > 1 and not raw_argv[1].startswith("-") else raw_argv[1:]
        return cmd, path, rem

    # Pattern: python analyze.py <path> <command> [args...]
    if len(raw_argv) > 1 and raw_argv[1] in COMMANDS:
        path = first
        cmd = raw_argv[1]
        rem = raw_argv[2:]
        return cmd, path, rem

    # Default pattern: python analyze.py <path> [flags...]
    path = first
    cmd = "analyze"
    rem = raw_argv[1:]
    return cmd, path, rem


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="analyze",
        description="Enterprise AI Legacy Software Intelligence CLI. No paid APIs required.",
    )
    parser.add_argument("path", help="Path to local repository directory or .zip archive")
    parser.add_argument(
        "subcommand",
        nargs="?",
        default="analyze",
        choices=list(COMMANDS),
        help="Subcommand to execute (default: analyze)",
    )
    parser.add_argument(
        "extra_args",
        nargs="*",
        help="Additional arguments for subcommands (e.g. question, class name, endpoint)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON output",
    )
    parser.add_argument(
        "--persist",
        action="store_true",
        help="Save analysis snapshot to PostgreSQL (run Alembic migrations first)",
    )
    parser.add_argument(
        "--project-name",
        help="Project name to associate with the saved repository",
    )
    parser.add_argument(
        "--database-url",
        help="Override DATABASE_URL for this run",
    )
    parser.add_argument(
        "--scan-only",
        action="store_true",
        help="Skip Java parsing (inventory scan only)",
    )
    parser.add_argument(
        "--list-files",
        action="store_true",
        help="List discovered file paths under each category",
    )
    parser.add_argument(
        "--list-types",
        action="store_true",
        help="List discovered packages, classes, interfaces, and endpoints",
    )
    parser.add_argument(
        "--verify-arch",
        action="store_true",
        help="Verify Controller -> Service -> Repository -> Database relationships",
    )
    parser.add_argument(
        "--trace-request",
        metavar="ENDPOINT",
        help="Trace request flow from endpoint/controller down to database table",
    )
    parser.add_argument(
        "--impact",
        metavar="SYMBOL",
        help="Run change-impact analysis for a class or method symbol",
    )
    parser.add_argument(
        "--neighbors",
        metavar="SYMBOL",
        help="Show direct incoming and outgoing neighbors of a symbol",
    )
    parser.add_argument(
        "--format",
        choices=["markdown", "json"],
        default="markdown",
        help="Output format for report command (markdown | json)",
    )
    parser.add_argument(
        "--output",
        "-o",
        help="File path to save the generated report",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    _configure_stdout()
    raw_args = list(sys.argv[1:] if argv is None else argv)

    # Allow --help / -h directly
    if "--help" in raw_args or "-h" in raw_args:
        build_parser().print_help()
        return 0

    cmd, path_str, rem_args = _normalize_cli_args(raw_args)

    # Re-parse options and remaining arguments
    parser = build_parser()
    reconstructed = [path_str, cmd] + rem_args
    args = parser.parse_args(reconstructed)

    target = Path(args.path)

    try:
        scan = scan_path(target)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    parse_result = None
    graph = None
    if not args.scan_only and scan.java_files:
        parse_result = parse_java_files(scan.root, scan.java_files)
        graph = extract_dependencies(parse_result)

    persisted = None
    if args.persist:
        try:
            with session_scope(args.database_url) as session:
                persisted = persist_analysis(
                    session,
                    scan,
                    parse_result,
                    graph,
                    project_name=args.project_name,
                )
        except Exception as exc:  # noqa: BLE001
            print(
                "Persistence failed "
                f"({type(exc).__name__}). Confirm PostgreSQL is running and migrations are applied.",
                file=sys.stderr,
            )
            return 2

    # -----------------------------------------------------------------------
    # Subcommand Dispatch
    # -----------------------------------------------------------------------

    # 1. analyze (default milestone scan)
    if cmd == "analyze":
        if args.json:
            payload = {
                "source": scan.source,
                "root": scan.root,
                "from_zip": scan.from_zip,
                "total_files": scan.total_files,
                "java_files": scan.java_files,
                "configuration_files": scan.configuration_files,
                "sql_files": scan.sql_files,
                "documentation_files": scan.documentation_files,
                "ignored_dirs": scan.ignored_dirs,
                "parse": parse_result.to_dict() if parse_result else None,
                "graph": graph.to_dict() if graph else None,
                "architecture_verified": len(verify_controller_service_repository(graph)) if graph else 0,
                "risks": analyze_risks(parse_result, graph).to_dict() if graph else None,
                "persistence": (
                    {
                        "project_id": persisted.project_id,
                        "repository_id": persisted.repository_id,
                        "analysis_run_id": persisted.analysis_run_id,
                    }
                    if persisted
                    else None
                ),
            }
            _safe_print(json.dumps(payload, indent=2))
            return 0

        _safe_print(f"Source: {scan.source}")
        if scan.from_zip:
            _safe_print(f"Extracted to: {scan.extract_dir}")
        _safe_print(f"Root: {scan.root}")
        _safe_print("")

        # 9 Milestone Checkmarks
        _safe_print(f"✓ Repository scanned ({scan.total_files} files)")
        if parse_result:
            _safe_print(f"✓ Java files parsed ({len(scan.java_files)})")
            _safe_print(f"✓ Packages discovered ({len(parse_result.packages)})")
            _safe_print(f"✓ Classes discovered ({len(parse_result.classes)})")
            _safe_print(f"✓ Methods discovered ({len(parse_result.methods)})")
            total_imports = sum(len(f.imports) for f in parse_result.files)
            _safe_print(f"✓ Imports extracted ({total_imports})")
        if graph:
            s = graph.summary()
            _safe_print(f"✓ Dependencies extracted ({s['total_edges']} relationships)")
            chains = verify_controller_service_repository(graph)
            _safe_print(f"✓ Architecture generated ({len(chains)} verified Controller->Service->Repo chains)")
            risks = analyze_risks(parse_result, graph)
            _safe_print(f"✓ Risk analysis complete ({risks.total_findings} findings)")

        if persisted is not None:
            _safe_print(
                "✓ Results persisted "
                f"(project={persisted.project_id}, repository={persisted.repository_id}, "
                f"analysis_run={persisted.analysis_run_id})"
            )

        # Handle optional flags passed to analyze
        if args.verify_arch and graph:
            _safe_print("")
            _safe_print("=== Architecture Verification ===")
            for c in verify_controller_service_repository(graph):
                _safe_print(f"  [OK] {c.summary_line()}")

        if args.trace_request and graph:
            _safe_print("")
            flow = trace_request_flow(graph, args.trace_request)
            for line in flow.summary_lines():
                _safe_print(f"  {line}")

        if args.impact and graph:
            _safe_print("")
            imp = impact_traversal(graph, args.impact)
            for line in imp.summary_lines():
                _safe_print(f"  {line}")

        if args.neighbors and graph:
            _safe_print("")
            _show_neighbors(graph, args.neighbors)

        return 0

    # 2. inspect
    if cmd == "inspect":
        _safe_print(f"=== Repository Inspection: {scan.source} ===")
        _safe_print(f"Files: {scan.total_files} total (Java: {len(scan.java_files)}, Config: {len(scan.configuration_files)}, SQL: {len(scan.sql_files)}, Docs: {len(scan.documentation_files)})")
        if parse_result:
            _safe_print(f"Structure: {len(parse_result.packages)} packages, {len(parse_result.classes)} classes, {len(parse_result.interfaces)} interfaces, {len(parse_result.endpoints)} REST endpoints")
            if parse_result.database_references:
                _safe_print(f"Database References ({len(parse_result.database_references)}):")
                for ref in parse_result.database_references:
                    _safe_print(f"  - {ref.kind}: {ref.name} (owner: {ref.owning_type})")
        if graph:
            chains = verify_controller_service_repository(graph)
            _safe_print(f"Verified Architectural Chains: {len(chains)}")
            for c in chains:
                _safe_print(f"  - {c.summary_line()}")
        return 0

    # 3. list-classes
    if cmd == "list-classes":
        if not parse_result:
            _safe_print("No Java classes discovered.")
            return 0
        _safe_print(f"Discovered Classes and Types ({len(parse_result.classes) + len(parse_result.interfaces)}):")
        for cls in parse_result.classes:
            anns = f" [{' '.join('@' + a.name for a in cls.annotations)}]" if cls.annotations else ""
            _safe_print(f"  [class] {cls.qualified_name}{anns} ({len(cls.methods)} methods)")
        for iface in parse_result.interfaces:
            ext = f" extends {', '.join(iface.extends)}" if iface.extends else ""
            _safe_print(f"  [interface] {iface.qualified_name}{ext}")
        return 0

    # 4. list-methods
    if cmd == "list-methods":
        if not parse_result:
            _safe_print("No Java methods discovered.")
            return 0
        _safe_print(f"Discovered Methods ({len(parse_result.methods)}):")
        for m in parse_result.methods:
            anns = f" [{' '.join('@' + a.name for a in m.annotations)}]" if m.annotations else ""
            ret = f"{m.return_type} " if m.return_type else ""
            _safe_print(f"  {ret}{m.signature}{anns}")
        return 0

    # 5. show-class
    if cmd == "show-class":
        if not args.extra_args:
            print("Error: show-class requires a class name. Example: python analyze.py <path> show-class PaymentController", file=sys.stderr)
            return 1
        target_name = args.extra_args[0]
        if not parse_result or not graph:
            _safe_print(f"Class '{target_name}' not found.")
            return 1

        matches = [c for c in parse_result.classes if c.name == target_name or c.qualified_name == target_name]
        if not matches:
            matches = [i for i in parse_result.interfaces if i.name == target_name or i.qualified_name == target_name]

        if not matches:
            _safe_print(f"Class or interface '{target_name}' not found in parsed repository.")
            return 1

        cls = matches[0]
        _safe_print(f"Class: {cls.name}")
        _safe_print(f"Kind: {cls.kind}")
        _safe_print(f"Qualified Name: {cls.qualified_name}")
        src_file = cls.source.file_path if cls.source else "unknown"
        lines_str = f"lines {cls.source.start_line}-{cls.source.end_line}" if cls.source else "lines unknown"
        _safe_print(f"Source: {src_file} ({lines_str})")
        if cls.annotations:
            _safe_print(f"Annotations: {', '.join('@' + a.name for a in cls.annotations)}")
        if cls.extends:
            _safe_print(f"Extends: {', '.join(cls.extends)}")
        if cls.implements:
            _safe_print(f"Implements: {', '.join(cls.implements)}")
        _safe_print(f"Fields ({len(cls.fields)}):")
        for f in cls.fields:
            _safe_print(f"  - {f.type_name} {f.name}")
        _safe_print(f"Methods ({len(cls.methods)}):")
        for m in cls.methods:
            _safe_print(f"  - {m.signature}")

        node = graph.get_node(f"type:{cls.qualified_name}") or graph.get_node(cls.name)
        if node:
            out_deps = graph.outgoing_edges(node.id, RelationshipType.DEPENDS_ON)
            if out_deps:
                _safe_print("Dependencies:")
                for d in out_deps:
                    target_n = graph.get_node(d.target_id)
                    _safe_print(f"  -> {target_n.name if target_n else d.target_id}")
        return 0

    # 6. show-dependencies
    if cmd == "show-dependencies":
        if not graph:
            _safe_print("Dependency graph not available.")
            return 1
        symbol = args.extra_args[0] if args.extra_args else None
        if symbol:
            _show_neighbors(graph, symbol)
        else:
            s = graph.summary()
            _safe_print("=== Repository Dependency Summary ===")
            _safe_print(f"Total Nodes: {s['total_nodes']}, Total Relationships: {s['total_edges']}")
            _safe_print(f"Resolved: {s['resolved_edges']}, Unresolved: {s['unresolved_edges']}")
            _safe_print("Relationship Breakdown:")
            for rel, count in s["edges_by_relationship"].items():
                _safe_print(f"  - {rel}: {count}")
        return 0

    # 7. show-graph
    if cmd == "show-graph":
        if not graph:
            _safe_print("Graph not available.")
            return 1
        s = graph.summary()
        _safe_print(f"=== Software Knowledge Graph ({s['total_nodes']} nodes, {s['total_edges']} edges) ===")
        _safe_print("Nodes by kind:")
        for k, v in s["nodes_by_kind"].items():
            _safe_print(f"  - {k}: {v}")
        _safe_print("Edges by relationship:")
        for r, v in s["edges_by_relationship"].items():
            _safe_print(f"  - {r}: {v}")
        return 0

    # 8. trace-request
    if cmd == "trace-request":
        if not args.extra_args:
            print("Error: trace-request requires an endpoint or path. Example: python analyze.py <path> trace-request /api/payment", file=sys.stderr)
            return 1
        endpoint = args.extra_args[0]
        if not graph:
            _safe_print("Knowledge graph not available.")
            return 1
        flow = trace_request_flow(graph, endpoint)
        for line in flow.summary_lines():
            _safe_print(line)
        return 0

    # 9. impact
    if cmd == "impact":
        if not args.extra_args:
            print("Error: impact requires a target symbol. Example: python analyze.py <path> impact PaymentService.processPayment", file=sys.stderr)
            return 1
        symbol = args.extra_args[0]
        if not graph:
            _safe_print("Knowledge graph not available.")
            return 1
        imp = impact_traversal(graph, symbol)
        for line in imp.summary_lines():
            _safe_print(line)
        _safe_print("")

        from app.analysis.impact import analyze_change_impact

        imp_res = analyze_change_impact(graph, symbol)
        _safe_print(f"Detailed Change Impact for: {imp_res.target} ({imp_res.target_kind})")
        if imp_res.target_file:
            _safe_print(f"Source file: {imp_res.target_file}")
        _safe_print(f"\nDirectly Affected (Depth 1): {len(imp_res.direct_impact)}")
        for item in imp_res.direct_impact:
            _safe_print(f"  - [{item.get('relationship') or 'DEPENDS_ON'}] {item['name']} ({item['kind']}) in {item.get('file_path') or 'N/A'}")
        _safe_print(f"\nIndirectly Affected (Depth > 1): {len(imp_res.indirect_impact)}")
        for item in imp_res.indirect_impact:
            _safe_print(f"  - [depth {item['depth']}] {item['name']} ({item['kind']}) in {item.get('file_path') or 'N/A'}")
        _safe_print(f"\nAffected APIs / Endpoints: {len(imp_res.affected_apis)}")
        for item in imp_res.affected_apis:
            _safe_print(f"  - {item['name']} in {item.get('file_path') or 'N/A'}")
        _safe_print(f"\nAffected Database Objects: {len(imp_res.affected_database_objects)}")
        for item in imp_res.affected_database_objects:
            _safe_print(f"  - {item['name']} ({item['kind']}) via {item.get('relationship')}")
        _safe_print(f"\nAffected Tests: {len(imp_res.affected_tests)}")
        for item in imp_res.affected_tests:
            _safe_print(f"  - {item['name']} in {item.get('file_path') or 'N/A'}")
        if imp_res.limitations:
            _safe_print("\nLimitations / Notes:")
            for lim in imp_res.limitations:
                _safe_print(f"  - {lim}")
        return 0

    # 10. risks
    if cmd == "risks":
        report = analyze_risks(parse_result, graph)
        for line in report.summary_lines():
            _safe_print(line)
        return 0

    # 11. ask
    if cmd == "ask":
        if not args.extra_args:
            print("Error: ask requires a question string. Example: python analyze.py <path> ask 'How does /api/payment reach the database?'", file=sys.stderr)
            return 1
        question = " ".join(args.extra_args)
        ans = answer_question(question, parse_result, graph)
        for line in ans.summary_lines():
            _safe_print(line)
        return 0

    # 12. report
    if cmd == "report":
        fmt = getattr(args, "format", "markdown")
        if fmt == "json":
            rep_text = generate_json_report(scan, parse_result, graph)
        else:
            rep_text = generate_markdown_report(scan, parse_result, graph)

        if args.output:
            out_p = Path(args.output)
            out_p.parent.mkdir(parents=True, exist_ok=True)
            out_p.write_text(rep_text, encoding="utf-8")
            _safe_print(f"Report written to: {out_p}")
        else:
            _safe_print(rep_text)
        return 0

    # 13. architecture
    if cmd == "architecture":
        from app.analysis.architecture import build_architecture_view

        arch = build_architecture_view(graph, parse_result)
        _safe_print("=== Architectural Inventory ===")
        _safe_print(f"Packages ({len(arch.packages)}): {', '.join(p['name'] for p in arch.packages[:8])}")
        _safe_print(f"Modules ({len(arch.modules)}): {', '.join(m['name'] for m in arch.modules)}")
        _safe_print(f"\nControllers ({len(arch.controllers)}):")
        for c in arch.controllers:
            _safe_print(f"  - {c['name']} (endpoints: {len(c.get('endpoints', []))})")
        _safe_print(f"\nServices ({len(arch.services)}):")
        for s in arch.services:
            _safe_print(f"  - {s['name']}")
        _safe_print(f"\nRepositories ({len(arch.repositories)}):")
        for r in arch.repositories:
            _safe_print(f"  - {r['name']} (tables: {', '.join(r.get('tables_queried', []))})")
        _safe_print(f"\nDatabases / Tables ({len(arch.databases)}):")
        for d in arch.databases:
            _safe_print(f"  - {d['name']}")
        _safe_print(f"\nExposed APIs ({len(arch.apis)}):")
        for a in arch.apis:
            _safe_print(f"  - {a['name']} -> {a['controller']}")
        _safe_print(f"\nExternal Integrations ({len(arch.external_integrations)}):")
        for e in arch.external_integrations:
            _safe_print(f"  - {e['name']} ({e['type']})")
        _safe_print(f"\nTests ({len(arch.tests)}):")
        for t in arch.tests:
            _safe_print(f"  - {t['name']}")
        _safe_print(f"\nArchitecture Chains Verified: {len(arch.chains)}")
        for ch in arch.chains:
            _safe_print(f"  - [{ch['endpoint']}] {ch['controller']} -> {ch['service']} -> {ch['repository']} -> [{ch['database_table']}]")
        return 0

    return 0


def _show_neighbors(graph, symbol: str) -> None:
    matched = graph.find_nodes(name=symbol)
    if not matched:
        matched = [n for n in graph.nodes if symbol in n.id]
    if matched:
        for target_n in matched:
            _safe_print(f"Node: [{target_n.kind}] {target_n.id}")
            out_n = get_direct_neighbors(graph, target_n.id, direction="outgoing")
            in_n = get_direct_neighbors(graph, target_n.id, direction="incoming")
            _safe_print(f"  Outgoing dependencies/calls ({len(out_n)}):")
            for n in out_n[:12]:
                rel = n.edge.relationship.value if hasattr(n.edge.relationship, "value") else str(n.edge.relationship)
                _safe_print(f"    --[{rel}]--> [{n.node.kind}] {n.node.name}")
            _safe_print(f"  Incoming callers/dependents ({len(in_n)}):")
            for n in in_n[:12]:
                rel = n.edge.relationship.value if hasattr(n.edge.relationship, "value") else str(n.edge.relationship)
                _safe_print(f"    <--[{rel}]-- [{n.node.kind}] {n.node.name}")
    else:
        _safe_print(f"Symbol '{symbol}' not found in dependency graph.")


if __name__ == "__main__":
    raise SystemExit(main())
