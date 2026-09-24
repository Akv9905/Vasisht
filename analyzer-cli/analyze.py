#!/usr/bin/env python3
"""
Enterprise AI analyzer CLI (P0/P1).

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
        print(text.replace("✓", "[OK]").encode(sys.stdout.encoding or "ascii", errors="replace").decode(
            sys.stdout.encoding or "ascii", errors="replace"
        ))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="analyze",
        description="Scan a Java/Spring repository (directory or ZIP). No paid APIs required.",
    )
    parser.add_argument(
        "path",
        help="Path to a local repository directory or .zip archive",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON inventory instead of summary lines",
    )
    parser.add_argument(
        "--list-files",
        action="store_true",
        help="List discovered file paths under each category",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    _configure_stdout()
    args = build_parser().parse_args(argv)
    target = Path(args.path)

    try:
        result = scan_path(target)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 — surface scan failures cleanly in CLI
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        payload = {
            "source": result.source,
            "root": result.root,
            "from_zip": result.from_zip,
            "total_files": result.total_files,
            "java_files": result.java_files,
            "configuration_files": result.configuration_files,
            "sql_files": result.sql_files,
            "documentation_files": result.documentation_files,
            "ignored_dirs": result.ignored_dirs,
            "files": [
                {
                    "relative_path": f.relative_path,
                    "size_bytes": f.size_bytes,
                    "categories": f.categories,
                }
                for f in result.files
            ],
        }
        _safe_print(json.dumps(payload, indent=2))
        return 0

    _safe_print(f"Source: {result.source}")
    if result.from_zip:
        _safe_print(f"Extracted to: {result.extract_dir}")
    _safe_print(f"Root: {result.root}")
    _safe_print("")
    for line in result.summary_lines():
        _safe_print(line)

    if args.list_files:
        _safe_print("")
        _safe_print("Java files:")
        for path in result.java_files:
            _safe_print(f"  - {path}")
        _safe_print("Configuration:")
        for path in result.configuration_files:
            _safe_print(f"  - {path}")
        _safe_print("SQL:")
        for path in result.sql_files:
            _safe_print(f"  - {path}")
        _safe_print("Documentation:")
        for path in result.documentation_files:
            _safe_print(f"  - {path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
