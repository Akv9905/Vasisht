"""File-type detectors for repository inventory (deterministic, no LLM)."""

from __future__ import annotations

from pathlib import Path

JAVA_EXTENSIONS = {".java"}
SQL_EXTENSIONS = {".sql"}
DOC_EXTENSIONS = {".md", ".markdown", ".txt", ".rst", ".adoc"}
DOC_NAMES = {"readme", "changelog", "license", "contributing", "authors"}

CONFIG_EXTENSIONS = {
    ".yml",
    ".yaml",
    ".properties",
    ".xml",
    ".json",
    ".conf",
    ".ini",
    ".toml",
    ".env",
}
CONFIG_NAMES = {
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "settings.gradle",
    "settings.gradle.kts",
    "gradle.properties",
    "application.properties",
    "application.yml",
    "application.yaml",
    "bootstrap.properties",
    "bootstrap.yml",
    "bootstrap.yaml",
    "docker-compose.yml",
    "docker-compose.yaml",
    "dockerfile",
    "makefile",
}

BINARY_EXTENSIONS = {
    ".class",
    ".jar",
    ".war",
    ".ear",
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
    ".pdf",
    ".zip",
    ".tar",
    ".gz",
    ".7z",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
}


def is_binary_path(path: Path) -> bool:
    return path.suffix.lower() in BINARY_EXTENSIONS


def is_java_file(path: Path) -> bool:
    return path.suffix.lower() in JAVA_EXTENSIONS


def is_sql_file(path: Path) -> bool:
    return path.suffix.lower() in SQL_EXTENSIONS


def is_documentation_file(path: Path) -> bool:
    name = path.name.lower()
    stem = path.stem.lower()
    if path.suffix.lower() in DOC_EXTENSIONS:
        return True
    return stem in DOC_NAMES or name in DOC_NAMES


def is_configuration_file(path: Path) -> bool:
    name = path.name.lower()
    if name in CONFIG_NAMES:
        return True
    if name.startswith("application") and path.suffix.lower() in {
        ".properties",
        ".yml",
        ".yaml",
        ".json",
    }:
        return True
    # Build / dependency manifests
    if name in {"pom.xml", "build.gradle", "build.gradle.kts"}:
        return True
    return path.suffix.lower() in CONFIG_EXTENSIONS and not is_documentation_file(path)


def classify_file(path: Path) -> set[str]:
    """Return category labels for a file path."""
    labels: set[str] = set()
    if is_java_file(path):
        labels.add("java")
    if is_sql_file(path):
        labels.add("sql")
    if is_documentation_file(path):
        labels.add("documentation")
    if is_configuration_file(path):
        labels.add("configuration")
    if not labels:
        labels.add("other")
    return labels
