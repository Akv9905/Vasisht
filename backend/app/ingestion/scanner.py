"""Repository scanner: local directories and ZIP archives."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from app.config import get_settings
from app.ingestion.detectors import (
    classify_file,
    is_binary_path,
    is_configuration_file,
    is_documentation_file,
    is_java_file,
    is_sql_file,
)
from app.ingestion.zip_handler import cleanup_extract_dir, safe_extract_zip


@dataclass
class FileRecord:
    path: str
    relative_path: str
    size_bytes: int
    categories: list[str]


@dataclass
class ScanResult:
    source: str
    root: str
    files: list[FileRecord] = field(default_factory=list)
    java_files: list[str] = field(default_factory=list)
    configuration_files: list[str] = field(default_factory=list)
    sql_files: list[str] = field(default_factory=list)
    documentation_files: list[str] = field(default_factory=list)
    ignored_dirs: list[str] = field(default_factory=list)
    total_files: int = 0
    from_zip: bool = False
    extract_dir: str | None = None

    def summary_lines(self) -> list[str]:
        return [
            "✓ Repository scanned",
            f"✓ Files discovered ({self.total_files})",
            f"✓ Java files discovered ({len(self.java_files)})",
            f"✓ Configuration discovered ({len(self.configuration_files)})",
            f"✓ SQL discovered ({len(self.sql_files)})",
            f"✓ Documentation discovered ({len(self.documentation_files)})",
        ]


def _should_skip_dir(name: str, ignore_names: set[str]) -> bool:
    return name in ignore_names or name.startswith(".")


def _walk_repository(root: Path, ignore_names: set[str]) -> tuple[list[FileRecord], list[str]]:
    records: list[FileRecord] = []
    ignored: list[str] = []

    for current_str, dirnames, filenames in os.walk(root, topdown=True):
        current = Path(current_str)
        # Prune ignored directories in-place.
        kept: list[str] = []
        for d in dirnames:
            if _should_skip_dir(d, ignore_names):
                ignored.append(str((current / d).relative_to(root)).replace("\\", "/"))
            else:
                kept.append(d)
        dirnames[:] = kept

        for filename in filenames:
            path = current / filename
            if is_binary_path(path):
                continue
            try:
                size = path.stat().st_size
            except OSError:
                continue
            rel = str(path.relative_to(root)).replace("\\", "/")
            categories = sorted(classify_file(path))
            records.append(
                FileRecord(
                    path=str(path),
                    relative_path=rel,
                    size_bytes=size,
                    categories=categories,
                )
            )

    records.sort(key=lambda r: r.relative_path)
    return records, sorted(set(ignored))


def scan_directory(root: Path, ignore_names: set[str] | None = None) -> ScanResult:
    root = root.resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"Not a directory: {root}")

    settings = get_settings()
    ignore = ignore_names if ignore_names is not None else settings.ignore_dir_names

    records, ignored = _walk_repository(root, ignore)

    java = [r.relative_path for r in records if is_java_file(Path(r.relative_path))]
    config = [r.relative_path for r in records if is_configuration_file(Path(r.relative_path))]
    sql = [r.relative_path for r in records if is_sql_file(Path(r.relative_path))]
    docs = [r.relative_path for r in records if is_documentation_file(Path(r.relative_path))]

    return ScanResult(
        source=str(root),
        root=str(root),
        files=records,
        java_files=java,
        configuration_files=config,
        sql_files=sql,
        documentation_files=docs,
        ignored_dirs=ignored,
        total_files=len(records),
        from_zip=False,
    )


def scan_zip(zip_path: Path, extract_to: Path | None = None) -> ScanResult:
    zip_path = zip_path.resolve()
    extract_root = safe_extract_zip(zip_path, extract_to)
    try:
        # If the ZIP contains a single top-level directory, scan inside it.
        children = [p for p in extract_root.iterdir() if not p.name.startswith(".")]
        scan_root = children[0] if len(children) == 1 and children[0].is_dir() else extract_root
        result = scan_directory(scan_root)
        result.source = str(zip_path)
        result.from_zip = True
        result.extract_dir = str(extract_root)
        return result
    except Exception:
        cleanup_extract_dir(extract_root)
        raise


def scan_path(path: str | Path, cleanup_zip: bool = False) -> ScanResult:
    """
    Scan a local directory or ZIP archive.

    If cleanup_zip is True and the source was a ZIP, the extract directory is removed
    after scanning (inventory paths remain as relative names only).
    """
    target = Path(path).expanduser().resolve()
    if not target.exists():
        raise FileNotFoundError(f"Path not found: {target}")

    if target.is_file() and target.suffix.lower() == ".zip":
        result = scan_zip(target)
        if cleanup_zip and result.extract_dir:
            cleanup_extract_dir(Path(result.extract_dir))
            result.extract_dir = None
        return result

    if target.is_dir():
        return scan_directory(target)

    raise ValueError(f"Unsupported path (expected directory or .zip): {target}")
