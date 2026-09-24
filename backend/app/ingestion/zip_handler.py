"""Safe ZIP extraction with path-traversal protection."""

from __future__ import annotations

import shutil
import tempfile
import zipfile
from pathlib import Path


class UnsafeZipError(ValueError):
    """Raised when a ZIP archive contains unsafe paths."""


def _is_within_directory(base: Path, target: Path) -> bool:
    try:
        target.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


def validate_zip_member(member_name: str, destination: Path) -> Path:
    """
    Resolve a ZIP member path under destination and reject traversal / absolute paths.
    """
    # Zip members use forward slashes; reject Windows drive / UNC / absolute forms.
    normalized = member_name.replace("\\", "/")
    if normalized.startswith("/") or normalized.startswith("../") or "/../" in f"/{normalized}/":
        raise UnsafeZipError(f"Unsafe ZIP member path: {member_name!r}")
    if ":" in normalized.split("/")[0]:
        raise UnsafeZipError(f"Unsafe ZIP member path: {member_name!r}")

    target = (destination / normalized).resolve()
    if not _is_within_directory(destination, target):
        raise UnsafeZipError(f"ZIP member escapes destination: {member_name!r}")
    return target


def safe_extract_zip(zip_path: Path, destination: Path | None = None) -> Path:
    """
    Extract a ZIP archive safely into destination (or a new temp directory).

    Returns the path to the extraction root. Caller owns cleanup of temp dirs.
    """
    zip_path = zip_path.resolve()
    if not zip_path.is_file():
        raise FileNotFoundError(f"ZIP not found: {zip_path}")

    if destination is None:
        destination = Path(tempfile.mkdtemp(prefix="enterprise-ai-zip-"))
    else:
        destination.mkdir(parents=True, exist_ok=True)

    destination = destination.resolve()

    with zipfile.ZipFile(zip_path, "r") as zf:
        for info in zf.infolist():
            # Skip directory entries after validating their names.
            member = info.filename
            if not member or member.endswith("/"):
                if member:
                    validate_zip_member(member.rstrip("/"), destination)
                continue
            target = validate_zip_member(member, destination)
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info, "r") as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)

    return destination


def cleanup_extract_dir(path: Path) -> None:
    """Remove a temporary extraction directory if it exists."""
    if path.exists() and path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
