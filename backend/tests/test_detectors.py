"""Detector unit tests."""

from pathlib import Path

from app.ingestion.detectors import (
    classify_file,
    is_configuration_file,
    is_documentation_file,
    is_java_file,
    is_sql_file,
)


def test_java_detection():
    assert is_java_file(Path("Foo.java"))
    assert not is_java_file(Path("Foo.kt"))


def test_sql_detection():
    assert is_sql_file(Path("schema.sql"))
    assert not is_sql_file(Path("schema.txt"))


def test_documentation_detection():
    assert is_documentation_file(Path("README.md"))
    assert is_documentation_file(Path("docs/guide.txt"))
    assert not is_documentation_file(Path("Foo.java"))


def test_configuration_detection():
    assert is_configuration_file(Path("pom.xml"))
    assert is_configuration_file(Path("build.gradle"))
    assert is_configuration_file(Path("application.yml"))
    assert is_configuration_file(Path("application.properties"))
    assert not is_configuration_file(Path("README.md"))


def test_classify_java():
    assert "java" in classify_file(Path("src/Main.java"))
