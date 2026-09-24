"""Safe ZIP extraction tests."""

import zipfile
from pathlib import Path

import pytest

from app.ingestion.zip_handler import UnsafeZipError, safe_extract_zip


def test_safe_extract_normal(tmp_path: Path):
    zip_path = tmp_path / "ok.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("project/Hello.java", "class Hello {}")
        zf.writestr("project/pom.xml", "<project/>")

    dest = tmp_path / "out"
    root = safe_extract_zip(zip_path, dest)
    assert (root / "project" / "Hello.java").is_file()
    assert (root / "project" / "pom.xml").is_file()


def test_rejects_path_traversal(tmp_path: Path):
    zip_path = tmp_path / "evil.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("../escape.txt", "nope")

    with pytest.raises(UnsafeZipError):
        safe_extract_zip(zip_path, tmp_path / "out")


def test_rejects_absolute_member(tmp_path: Path):
    zip_path = tmp_path / "abs.zip"
    # Craft a member that looks absolute via leading slash.
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("/tmp/evil.txt", "nope")

    with pytest.raises(UnsafeZipError):
        safe_extract_zip(zip_path, tmp_path / "out")
