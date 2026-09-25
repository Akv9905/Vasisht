"""Repository-level Java parsing orchestration."""

from __future__ import annotations

from pathlib import Path

from app.parser.base import JavaParser, aggregate_parse_results
from app.parser.javalang_parser import JavalangJavaParser
from app.parser.models import ParseResult

_DEFAULT_PARSER: JavaParser | None = None


def get_default_parser() -> JavaParser:
    global _DEFAULT_PARSER
    if _DEFAULT_PARSER is None:
        _DEFAULT_PARSER = JavalangJavaParser()
    return _DEFAULT_PARSER


def parse_java_files(
    root: str | Path,
    java_relative_paths: list[str],
    *,
    parser: JavaParser | None = None,
) -> ParseResult:
    """Parse discovered Java files under a repository root."""
    active = parser or get_default_parser()
    return active.parse_files(Path(root), java_relative_paths)


def parse_repository_java(
    root: str | Path,
    *,
    parser: JavaParser | None = None,
) -> ParseResult:
    """Scan-free helper: parse every *.java file under root (ignores target/build via walk)."""
    from app.ingestion.scanner import scan_directory

    scan = scan_directory(Path(root))
    return parse_java_files(scan.root, scan.java_files, parser=parser)


__all__ = [
    "JavaParser",
    "JavalangJavaParser",
    "ParseResult",
    "aggregate_parse_results",
    "get_default_parser",
    "parse_java_files",
    "parse_repository_java",
]
