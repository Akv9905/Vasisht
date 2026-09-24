"""Repository scanner tests."""

import zipfile
from pathlib import Path

from app.ingestion.scanner import scan_directory, scan_path, scan_zip


def _make_mini_repo(root: Path) -> None:
    (root / "src" / "main" / "java" / "com" / "example").mkdir(parents=True)
    (root / "src" / "main" / "resources").mkdir(parents=True)
    (root / "docs").mkdir(parents=True)
    (root / "target" / "classes").mkdir(parents=True)
    (root / ".git").mkdir()

    (root / "pom.xml").write_text("<project/>", encoding="utf-8")
    (root / "src" / "main" / "java" / "com" / "example" / "App.java").write_text(
        "package com.example; class App {}",
        encoding="utf-8",
    )
    (root / "src" / "main" / "resources" / "application.yml").write_text(
        "server:\n  port: 8080\n",
        encoding="utf-8",
    )
    (root / "src" / "main" / "resources" / "schema.sql").write_text(
        "CREATE TABLE t (id INT);",
        encoding="utf-8",
    )
    (root / "README.md").write_text("# Mini", encoding="utf-8")
    (root / "docs" / "notes.md").write_text("notes", encoding="utf-8")
    (root / "target" / "classes" / "App.class").write_text("binary", encoding="utf-8")
    (root / ".git" / "config").write_text("git", encoding="utf-8")


def test_scan_directory_inventory(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _make_mini_repo(repo)

    result = scan_directory(repo)
    assert result.total_files >= 5
    assert any(p.endswith("App.java") for p in result.java_files)
    assert any(p.endswith("pom.xml") for p in result.configuration_files)
    assert any(p.endswith("application.yml") for p in result.configuration_files)
    assert any(p.endswith("schema.sql") for p in result.sql_files)
    assert any("README.md" in p for p in result.documentation_files)
    assert not any("target" in p for p in result.java_files)
    assert any(d == "target" or d.startswith("target/") for d in result.ignored_dirs) or "target" in result.ignored_dirs


def test_scan_path_directory(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _make_mini_repo(repo)
    result = scan_path(repo)
    assert "✓ Repository scanned" in result.summary_lines()[0]


def test_scan_zip(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _make_mini_repo(repo)
    zip_path = tmp_path / "repo.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for path in repo.rglob("*"):
            if path.is_file():
                zf.write(path, arcname=str(path.relative_to(tmp_path)).replace("\\", "/"))

    result = scan_zip(zip_path, tmp_path / "extract")
    assert result.from_zip is True
    assert len(result.java_files) >= 1
    assert len(result.configuration_files) >= 1


def test_sample_payment_service_exists():
    sample = Path(__file__).resolve().parents[2] / "sample-projects" / "payment-service"
    assert sample.is_dir(), "sample-projects/payment-service must exist"
    result = scan_path(sample)
    assert len(result.java_files) >= 5
    assert any("pom.xml" in p or p.endswith("pom.xml") for p in result.configuration_files)
    assert len(result.sql_files) >= 1
    assert len(result.documentation_files) >= 1
