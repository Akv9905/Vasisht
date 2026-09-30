"""Upload limits, file validation, and temporary file cleanup (P19).

Enforces:
- Maximum upload file size limits
- Whitelisted file extensions
- Deterministic cleanup of temporary directories and extraction artifacts
"""

from __future__ import annotations

import contextlib
import os
from pathlib import Path
import shutil
import tempfile
from typing import Generator

from fastapi import HTTPException, UploadFile, status

# Default 100MB limit for ZIP uploads
DEFAULT_MAX_UPLOAD_BYTES = 100 * 1024 * 1024

ALLOWED_UPLOAD_EXTENSIONS = {
    ".zip",
    ".jar",
    ".tar",
    ".gz",
    ".java",
    ".xml",
    ".json",
    ".properties",
    ".yaml",
    ".yml",
    ".sql",
    ".md",
}


def validate_upload_filename(filename: str) -> str:
    """Validate that filename has an allowed extension and no path traversal attempts."""
    if not filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing upload filename.",
        )

    clean_name = os.path.basename(filename)
    if ".." in filename or "/" in filename or "\\" in filename:
        clean_name = os.path.basename(filename.replace("\\", "/"))

    ext = Path(clean_name).suffix.lower()
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file extension '{ext}'. Allowed: {', '.join(sorted(ALLOWED_UPLOAD_EXTENSIONS))}",
        )

    return clean_name


def validate_upload_size(size_bytes: int, max_bytes: int = DEFAULT_MAX_UPLOAD_BYTES) -> None:
    """Ensure upload does not exceed configured byte limits."""
    if size_bytes > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Upload exceeds maximum permitted size of {max_bytes / (1024*1024):.1f} MB.",
        )


@contextlib.contextmanager
def temporary_upload_directory(prefix: str = "ea_upload_") -> Generator[Path, None, None]:
    """Context manager creating a temporary workspace directory guaranteed to be purged on exit."""
    temp_dir = Path(tempfile.mkdtemp(prefix=prefix))
    try:
        yield temp_dir
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
