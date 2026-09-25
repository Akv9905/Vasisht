"""Java parser unit and sample-project tests (P2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.parser import JavalangJavaParser, parse_java_files, parse_repository_java
from app.parser.spring import join_paths

SAMPLE_ROOT = Path(__file__).resolve().parents[2] / "sample-projects" / "payment-service"

CONTROLLER_SRC = """\
package com.example.demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/demo")
public class DemoController extends BaseController implements DemoApi {

    private final DemoService demoService;

    public DemoController(DemoService demoService) {
        this.demoService = demoService;
    }

    @GetMapping("/hello")
    public String hello() {
        return demoService.greet();
    }
}
"""

ENTITY_SRC = """\
package com.example.demo;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Table;

@Entity
@Table(name = "demos")
public class DemoEntity {
    @Column(name = "demo_name")
    private String name;

    public String getName() { return name; }
}
"""

INTERFACE_SRC = """\
package com.example.demo;

import org.springframework.stereotype.Repository;

@Repository
public interface DemoRepository extends CrudRepository<DemoEntity, Long> {
    DemoEntity findByName(String name);
}
"""

ENUM_SRC = """\
package com.example.demo;

public enum DemoStatus {
    NEW,
    DONE
}
"""


@pytest.fixture
def parser() -> JavalangJavaParser:
    return JavalangJavaParser()


def test_parser_abstraction_name(parser: JavalangJavaParser):
    assert parser.name == "javalang"


def test_parse_package_imports_class(parser: JavalangJavaParser):
    parsed = parser.parse_source(CONTROLLER_SRC, "DemoController.java")
    assert parsed.parse_error is None
    assert parsed.package == "com.example.demo"
    assert any(i.path.endswith("RestController") for i in parsed.imports)
    assert len(parsed.types) == 1
    cls = parsed.types[0]
    assert cls.name == "DemoController"
    assert cls.kind == "class"
    assert cls.qualified_name == "com.example.demo.DemoController"
    assert cls.source is not None
    assert cls.source.file_path == "DemoController.java"


def test_extract_inheritance_and_implements(parser: JavalangJavaParser):
    cls = parser.parse_source(CONTROLLER_SRC, "DemoController.java").types[0]
    assert cls.extends == ["BaseController"]
    assert cls.implements == ["DemoApi"]


def test_extract_fields_methods_constructors(parser: JavalangJavaParser):
    cls = parser.parse_source(CONTROLLER_SRC, "DemoController.java").types[0]
    assert any(f.name == "demoService" for f in cls.fields)
    assert len(cls.constructors) == 1
    assert cls.constructors[0].is_constructor
    assert cls.constructors[0].signature.startswith("DemoController(")
    hello = next(m for m in cls.methods if m.name == "hello")
    assert hello.return_type == "String"
    assert hello.signature == "String hello()"
    assert hello.source is not None
    assert any(c.name == "greet" for c in hello.method_calls)


def test_extract_annotations_and_spring(parser: JavalangJavaParser):
    parsed = parser.parse_source(CONTROLLER_SRC, "DemoController.java")
    names = {a.name.split(".")[-1] for a in parsed.spring_annotations}
    assert "RestController" in names
    assert "RequestMapping" in names
    assert "GetMapping" in names


def test_extract_rest_endpoints(parser: JavalangJavaParser):
    parsed = parser.parse_source(CONTROLLER_SRC, "DemoController.java")
    assert len(parsed.endpoints) == 1
    ep = parsed.endpoints[0]
    assert ep.http_method == "GET"
    assert ep.path == "/api/demo/hello"
    assert ep.handler_method == "hello"
    assert ep.source is not None


def test_extract_interface(parser: JavalangJavaParser):
    parsed = parser.parse_source(INTERFACE_SRC, "DemoRepository.java")
    iface = parsed.types[0]
    assert iface.kind == "interface"
    assert iface.extends == ["CrudRepository<DemoEntity, Long>"]
    assert any(m.name == "findByName" for m in iface.methods)
    assert any(a.name.endswith("Repository") for a in iface.annotations)


def test_extract_enum(parser: JavalangJavaParser):
    parsed = parser.parse_source(ENUM_SRC, "DemoStatus.java")
    enum_type = parsed.types[0]
    assert enum_type.kind == "enum"
    names = {f.name for f in enum_type.fields}
    assert "NEW" in names
    assert "DONE" in names


def test_extract_database_references(parser: JavalangJavaParser):
    parsed = parser.parse_source(ENTITY_SRC, "DemoEntity.java")
    kinds = {(r.kind, r.name) for r in parsed.database_references}
    assert ("entity", "DemoEntity") in kinds
    assert ("table", "demos") in kinds
    assert ("column", "demo_name") in kinds


def test_parse_error_does_not_crash(parser: JavalangJavaParser):
    parsed = parser.parse_source("not valid java {{{", "Bad.java")
    assert parsed.parse_error is not None
    assert parsed.types == []


def test_join_paths():
    assert join_paths("/api", "payment") == "/api/payment"
    assert join_paths("/api/", "/payment/") == "/api/payment"
    assert join_paths("", "") == "/"


def test_sample_payment_service_parse():
    assert SAMPLE_ROOT.is_dir()
    result = parse_repository_java(SAMPLE_ROOT)

    assert result.files_failed == 0
    assert result.files_parsed >= 9
    assert "com.example.payment.controller" in result.packages
    assert "com.example.payment.service" in result.packages

    class_names = {c.name for c in result.classes}
    assert "PaymentController" in class_names
    assert "PaymentService" in class_names
    assert "PaymentEntity" in class_names
    assert "MetricsFacade" in class_names

    interface_names = {i.name for i in result.interfaces}
    assert "PaymentRepository" in interface_names

    method_names = {m.name for m in result.methods}
    assert "processPayment" in method_names
    assert "create" in method_names
    assert "notifyPaymentCreated" in method_names

    assert any(i.path.endswith("PaymentService") for i in result.imports)

    endpoint_paths = {(e.http_method, e.path) for e in result.endpoints}
    assert ("POST", "/api/payment") in endpoint_paths
    assert ("POST", "/api/refund/{paymentId}") in endpoint_paths

    table_names = {r.name for r in result.database_references if r.kind == "table"}
    assert "payments" in table_names

    # Every type retains source-file information
    for t in result.classes + result.interfaces + result.enums:
        assert t.source is not None
        assert t.source.file_path.endswith(".java")


def test_parse_java_files_uses_relative_paths():
    from app.ingestion.scanner import scan_directory

    scan = scan_directory(SAMPLE_ROOT)
    result = parse_java_files(scan.root, scan.java_files)
    assert result.files_parsed == len(scan.java_files)
    assert all("/" in f.file_path or f.file_path.endswith(".java") for f in result.files)
