#!/usr/bin/env python3
"""
Enterprise AI analyzer CLI (P0–P2).

Usage:
  python analyzer-cli/analyze.py ./sample-projects/payment-service
  python analyzer-cli/analyze.py ./repository.zip
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

from app.ingestion.scanner import scan_path  # noqa: E402
from app.parser import parse_java_files  # noqa: E402


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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="analyze",
        description="Scan and parse a Java/Spring repository. No paid APIs required.",
    )
    parser.add_argument(
        "path",
        help="Path to a local repository directory or .zip archive",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON (scan + parse) instead of summary lines",
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
        "--scan-only",
        action="store_true",
        help="Skip Java parsing (P1 inventory only)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    _configure_stdout()
    args = build_parser().parse_args(argv)
    target = Path(args.path)

    try:
        scan = scan_path(target)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 — surface scan failures cleanly in CLI
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    parse_result = None
    if not args.scan_only and scan.java_files:
        parse_result = parse_java_files(scan.root, scan.java_files)

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
            "files": [
                {
                    "relative_path": f.relative_path,
                    "size_bytes": f.size_bytes,
                    "categories": f.categories,
                }
                for f in scan.files
            ],
            "parse": parse_result.to_dict() if parse_result else None,
        }
        _safe_print(json.dumps(payload, indent=2))
        return 0

    _safe_print(f"Source: {scan.source}")
    if scan.from_zip:
        _safe_print(f"Extracted to: {scan.extract_dir}")
    _safe_print(f"Root: {scan.root}")
    _safe_print("")
    for line in scan.summary_lines():
        _safe_print(line)

    if parse_result is not None:
        for line in parse_result.summary_lines():
            _safe_print(line)

    if args.list_files:
        _safe_print("")
        _safe_print("Java files:")
        for path in scan.java_files:
            _safe_print(f"  - {path}")
        _safe_print("Configuration:")
        for path in scan.configuration_files:
            _safe_print(f"  - {path}")
        _safe_print("SQL:")
        for path in scan.sql_files:
            _safe_print(f"  - {path}")
        _safe_print("Documentation:")
        for path in scan.documentation_files:
            _safe_print(f"  - {path}")

    if args.list_types and parse_result is not None:
        _safe_print("")
        _safe_print("Packages:")
        for pkg in parse_result.packages:
            _safe_print(f"  - {pkg}")
        _safe_print("Classes:")
        for cls in parse_result.classes:
            _safe_print(f"  - {cls.qualified_name}")
        _safe_print("Interfaces:")
        for iface in parse_result.interfaces:
            _safe_print(f"  - {iface.qualified_name} extends={iface.extends}")
        _safe_print("Endpoints:")
        for ep in parse_result.endpoints:
            _safe_print(f"  - {ep.http_method} {ep.path} -> {ep.handler_class}.{ep.handler_method}")
        _safe_print("Database references:")
        for ref in parse_result.database_references:
            _safe_print(f"  - {ref.kind}: {ref.name} ({ref.owning_type})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
