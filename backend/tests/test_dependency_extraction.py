"""Dependency extraction tests (P3).

Tests cover:
- All 11 relationship types: CONTAINS, IMPORTS, EXTENDS, IMPLEMENTS,
  CALLS, USES, EXPOSES, QUERIES, DEPENDS_ON, REFERENCES, TESTS
- Type resolution (same-package, import-based, qualified-name)
- Unresolved relationship flagging
- DependencyGraph model helpers (add_node dedup, add_edge dedup, filters)
- extract_dependencies() convenience entry point
- Integration: payment-service sample project produces expected graph shape
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.graph.extractor import (
    DependencyExtractor,
    extract_all_type_tokens,
    extract_dependencies,
    extract_generic_arguments,
    strip_generics_and_arrays,
)
from app.graph.models import DependencyGraph, GraphEdge, GraphNode, RelationshipType
from app.parser import JavalangJavaParser, parse_java_files, parse_repository_java
from app.parser.models import ParseResult

SAMPLE_ROOT = Path(__file__).resolve().parents[2] / "sample-projects" / "payment-service"

# ---------------------------------------------------------------------------
# Inline Java source snippets for unit tests
# ---------------------------------------------------------------------------

CONTROLLER_SRC = """\
package com.example.app;

import com.example.app.service.AppService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/app")
public class AppController extends BaseController implements AppApi {

    private final AppService appService;

    public AppController(AppService appService) {
        this.appService = appService;
    }

    @GetMapping("/items")
    public String listItems() {
        return appService.fetchItems();
    }

    @PostMapping("/items")
    public String createItem() {
        return appService.createItem();
    }
}
"""

SERVICE_SRC = """\
package com.example.app.service;

import com.example.app.repository.AppRepository;
import org.springframework.stereotype.Service;

@Service
public class AppService {

    private final AppRepository appRepository;

    public AppService(AppRepository appRepository) {
        this.appRepository = appRepository;
    }

    public String fetchItems() {
        return appRepository.findAll().toString();
    }

    public String createItem() {
        return "created";
    }
}
"""

REPOSITORY_SRC = """\
package com.example.app.repository;

import com.example.app.entity.AppEntity;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

@Repository
public interface AppRepository extends JpaRepository<AppEntity, Long> {
    AppEntity findByName(String name);
}
"""

ENTITY_SRC = """\
package com.example.app.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Table;

@Entity
@Table(name = "app_items")
public class AppEntity {
    @Column(name = "item_name")
    private String name;

    public String getName() { return name; }
}
"""

TEST_SRC = """\
package com.example.app.service;

import org.junit.jupiter.api.Test;

public class AppServiceTest {

    @Test
    public void testFetchItems() {
        AppService svc = new AppService(null);
        svc.fetchItems();
    }
}
"""

INTERFACE_SRC = """\
package com.example.app;

public interface AppApi {
    String listItems();
}
"""

BASE_SRC = """\
package com.example.app;

public class BaseController {
    public void init() {}
}
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_parse_result(*sources: tuple[str, str]) -> ParseResult:
    """Parse multiple (source, filename) pairs into a single ParseResult."""
    from app.parser.models import ParseResult as PR

    parser = JavalangJavaParser()
    result = PR()
    for src, fname in sources:
        pf = parser.parse_source(src, fname)
        result.files.append(pf)
        if pf.parse_error:
            result.files_failed += 1
            continue
        result.files_parsed += 1
        if pf.package and pf.package not in result.packages:
            result.packages.append(pf.package)
        for t in pf.types:
            if t.kind == "class":
                result.classes.append(t)
            elif t.kind == "interface":
                result.interfaces.append(t)
            elif t.kind == "enum":
                result.enums.append(t)
            result.methods.extend(t.methods)
            result.constructors.extend(t.constructors)
            result.fields.extend(t.fields)
        result.imports.extend(pf.imports)
        result.endpoints.extend(pf.endpoints)
        result.database_references.extend(pf.database_references)
        result.spring_annotations.extend(pf.spring_annotations)
    return result


def _full_parse_result() -> ParseResult:
    return _make_parse_result(
        (CONTROLLER_SRC, "AppController.java"),
        (SERVICE_SRC, "AppService.java"),
        (REPOSITORY_SRC, "AppRepository.java"),
        (ENTITY_SRC, "AppEntity.java"),
        (TEST_SRC, "AppServiceTest.java"),
        (INTERFACE_SRC, "AppApi.java"),
        (BASE_SRC, "BaseController.java"),
    )


def _graph_from_full() -> DependencyGraph:
    return extract_dependencies(_full_parse_result())


# ---------------------------------------------------------------------------
# Utility function unit tests
# ---------------------------------------------------------------------------

class TestStripGenericsAndArrays:
    def test_simple_type(self):
        assert strip_generics_and_arrays("String") == "String"

    def test_generic_type(self):
        assert strip_generics_and_arrays("List<String>") == "List"

    def test_nested_generic(self):
        assert strip_generics_and_arrays("Map<String, List<Integer>>") == "Map"

    def test_array_type(self):
        assert strip_generics_and_arrays("String[]") == "String"

    def test_combined(self):
        assert strip_generics_and_arrays("List<String>[]") == "List"

    def test_empty(self):
        assert strip_generics_and_arrays("") == ""


class TestExtractGenericArguments:
    def test_single_arg(self):
        assert extract_generic_arguments("List<String>") == ["String"]

    def test_two_args(self):
        args = extract_generic_arguments("Map<String, Integer>")
        assert args == ["String", "Integer"]

    def test_jpa_repository(self):
        args = extract_generic_arguments("JpaRepository<AppEntity, Long>")
        assert args == ["AppEntity", "Long"]

    def test_no_generics(self):
        assert extract_generic_arguments("String") == []

    def test_nested_generics(self):
        args = extract_generic_arguments("Map<String, List<Integer>>")
        assert args == ["String", "List"]

    def test_empty(self):
        assert extract_generic_arguments("") == []


class TestExtractAllTypeTokens:
    def test_simple(self):
        assert "String" in extract_all_type_tokens("String")

    def test_generic(self):
        tokens = extract_all_type_tokens("Map<String, AppEntity>")
        assert "Map" in tokens
        assert "String" in tokens
        assert "AppEntity" in tokens

    def test_primitives_excluded(self):
        tokens = extract_all_type_tokens("int")
        assert tokens == []

    def test_empty(self):
        assert extract_all_type_tokens("") == []


# ---------------------------------------------------------------------------
# DependencyGraph model tests
# ---------------------------------------------------------------------------

class TestDependencyGraphModel:
    def test_add_node_dedup(self):
        g = DependencyGraph()
        n1 = GraphNode(id="type:A", kind="class", name="A")
        n2 = GraphNode(id="type:A", kind="class", name="A")
        g.add_node(n1)
        g.add_node(n2)
        assert len(g.nodes) == 1

    def test_add_node_merges_metadata(self):
        g = DependencyGraph()
        g.add_node(GraphNode(id="type:A", kind="class", name="A", metadata={"x": 1}))
        g.add_node(GraphNode(id="type:A", kind="class", name="A", metadata={"y": 2}))
        assert g.get_node("type:A").metadata == {"x": 1, "y": 2}

    def test_add_edge_dedup(self):
        g = DependencyGraph()
        e = GraphEdge(source_id="a", target_id="b", relationship=RelationshipType.CONTAINS)
        g.add_edge(e)
        g.add_edge(e)
        assert len(g.edges) == 1

    def test_get_node_returns_none_for_unknown(self):
        g = DependencyGraph()
        assert g.get_node("nonexistent") is None

    def test_find_nodes_by_kind(self):
        g = DependencyGraph()
        g.add_node(GraphNode(id="t:A", kind="class", name="A"))
        g.add_node(GraphNode(id="p:pkg", kind="package", name="pkg"))
        classes = g.find_nodes(kind="class")
        assert len(classes) == 1
        assert classes[0].name == "A"

    def test_find_nodes_by_name(self):
        g = DependencyGraph()
        g.add_node(GraphNode(id="t:A", kind="class", name="Foo"))
        g.add_node(GraphNode(id="t:B", kind="class", name="Bar"))
        assert len(g.find_nodes(name="Foo")) == 1

    def test_outgoing_edges_filtered_by_relationship(self):
        g = DependencyGraph()
        g.add_edge(GraphEdge("a", "b", RelationshipType.CONTAINS))
        g.add_edge(GraphEdge("a", "c", RelationshipType.IMPORTS))
        out = g.outgoing_edges("a", RelationshipType.CONTAINS)
        assert len(out) == 1
        assert out[0].target_id == "b"

    def test_incoming_edges(self):
        g = DependencyGraph()
        g.add_edge(GraphEdge("a", "b", RelationshipType.CONTAINS))
        g.add_edge(GraphEdge("c", "b", RelationshipType.IMPORTS))
        inc = g.incoming_edges("b")
        assert len(inc) == 2

    def test_resolved_and_unresolved_edges(self):
        g = DependencyGraph()
        g.add_edge(GraphEdge("a", "b", RelationshipType.CONTAINS, resolved=True))
        g.add_edge(GraphEdge("a", "c", RelationshipType.IMPORTS, resolved=False))
        assert len(g.resolved_edges()) == 1
        assert len(g.unresolved_edges()) == 1

    def test_summary_keys(self):
        g = _graph_from_full()
        s = g.summary()
        assert "total_nodes" in s
        assert "total_edges" in s
        assert "resolved_edges" in s
        assert "unresolved_edges" in s
        assert "nodes_by_kind" in s
        assert "edges_by_relationship" in s

    def test_to_dict_round_trip(self):
        g = _graph_from_full()
        d = g.to_dict()
        assert isinstance(d["nodes"], list)
        assert isinstance(d["edges"], list)
        # Every edge has a string relationship value
        for e in d["edges"]:
            assert isinstance(e["relationship"], str)


# ---------------------------------------------------------------------------
# Node creation tests
# ---------------------------------------------------------------------------

class TestNodeCreation:
    def test_package_nodes_created(self):
        g = _graph_from_full()
        pkg_ids = {n.id for n in g.find_nodes(kind="package")}
        assert "package:com.example.app" in pkg_ids
        assert "package:com.example.app.service" in pkg_ids
        assert "package:com.example.app.repository" in pkg_ids
        assert "package:com.example.app.entity" in pkg_ids

    def test_class_nodes_created(self):
        g = _graph_from_full()
        class_names = {n.name for n in g.find_nodes(kind="class")}
        assert "AppController" in class_names
        assert "AppService" in class_names
        assert "AppEntity" in class_names

    def test_interface_nodes_created(self):
        g = _graph_from_full()
        iface_names = {n.name for n in g.find_nodes(kind="interface")}
        assert "AppRepository" in iface_names
        assert "AppApi" in iface_names

    def test_method_nodes_created(self):
        g = _graph_from_full()
        method_names = {n.name for n in g.find_nodes(kind="method")}
        assert "listItems" in method_names
        assert "fetchItems" in method_names
        assert "createItem" in method_names

    def test_field_nodes_created(self):
        g = _graph_from_full()
        field_names = {n.name for n in g.find_nodes(kind="field")}
        assert "appService" in field_names
        assert "appRepository" in field_names

    def test_endpoint_nodes_created(self):
        g = _graph_from_full()
        ep_nodes = g.find_nodes(kind="endpoint")
        assert len(ep_nodes) >= 2
        ep_names = {n.name for n in ep_nodes}
        assert any("GET" in n for n in ep_names)
        assert any("POST" in n for n in ep_names)

    def test_database_table_node_created(self):
        g = _graph_from_full()
        tables = g.find_nodes(kind="database_table")
        assert len(tables) >= 1
        assert any(t.name == "app_items" for t in tables)

    def test_database_column_node_created(self):
        g = _graph_from_full()
        cols = g.find_nodes(kind="database_column")
        assert any(c.name == "item_name" for c in cols)

    def test_node_has_file_path(self):
        g = _graph_from_full()
        controller_node = next(n for n in g.nodes if n.name == "AppController")
        assert controller_node.file_path is not None
        assert "AppController" in controller_node.file_path


# ---------------------------------------------------------------------------
# Relationship: CONTAINS
# ---------------------------------------------------------------------------

class TestContainsRelationship:
    def test_package_contains_class(self):
        g = _graph_from_full()
        pkg_id = "package:com.example.app"
        cls_id = "type:com.example.app.AppController"
        edges = g.outgoing_edges(pkg_id, RelationshipType.CONTAINS)
        target_ids = {e.target_id for e in edges}
        assert cls_id in target_ids

    def test_file_contains_class(self):
        g = _graph_from_full()
        file_id = "file:AppController.java"
        edges = g.outgoing_edges(file_id, RelationshipType.CONTAINS)
        assert any(e.target_id == "type:com.example.app.AppController" for e in edges)

    def test_class_contains_fields(self):
        g = _graph_from_full()
        cls_id = "type:com.example.app.AppController"
        edges = g.outgoing_edges(cls_id, RelationshipType.CONTAINS)
        target_ids = {e.target_id for e in edges}
        assert "field:com.example.app.AppController.appService" in target_ids

    def test_class_contains_methods(self):
        g = _graph_from_full()
        cls_id = "type:com.example.app.AppController"
        edges = g.outgoing_edges(cls_id, RelationshipType.CONTAINS)
        target_ids = {e.target_id for e in edges}
        assert "method:com.example.app.AppController#listItems" in target_ids
        assert "method:com.example.app.AppController#createItem" in target_ids

    def test_table_contains_column(self):
        g = _graph_from_full()
        tbl_id = "table:app_items"
        edges = g.outgoing_edges(tbl_id, RelationshipType.CONTAINS)
        assert any("item_name" in e.target_id for e in edges)

    def test_all_contains_edges_resolved(self):
        g = _graph_from_full()
        contains_edges = [e for e in g.edges if e.relationship == RelationshipType.CONTAINS]
        unresolved = [e for e in contains_edges if not e.resolved]
        assert unresolved == [], f"Unexpected unresolved CONTAINS edges: {unresolved}"


# ---------------------------------------------------------------------------
# Relationship: IMPORTS
# ---------------------------------------------------------------------------

class TestImportsRelationship:
    def test_file_imports_edges_exist(self):
        g = _graph_from_full()
        file_id = "file:AppController.java"
        edges = g.outgoing_edges(file_id, RelationshipType.IMPORTS)
        assert len(edges) >= 1

    def test_resolved_internal_import(self):
        g = _graph_from_full()
        # AppController imports AppService which is in the parse result
        cls_id = "type:com.example.app.AppController"
        edges = g.outgoing_edges(cls_id, RelationshipType.IMPORTS)
        resolved = [e for e in edges if e.resolved]
        target_ids = {e.target_id for e in resolved}
        assert "type:com.example.app.service.AppService" in target_ids

    def test_unresolved_external_import(self):
        g = _graph_from_full()
        # Spring annotations are external
        file_id = "file:AppController.java"
        edges = g.outgoing_edges(file_id, RelationshipType.IMPORTS)
        external = [e for e in edges if not e.resolved]
        assert len(external) >= 1

    def test_import_metadata_has_path(self):
        g = _graph_from_full()
        file_id = "file:AppController.java"
        edges = g.outgoing_edges(file_id, RelationshipType.IMPORTS)
        assert all("import_path" in e.metadata for e in edges)


# ---------------------------------------------------------------------------
# Relationship: EXTENDS
# ---------------------------------------------------------------------------

class TestExtendsRelationship:
    def test_class_extends_known_class(self):
        g = _graph_from_full()
        cls_id = "type:com.example.app.AppController"
        edges = g.outgoing_edges(cls_id, RelationshipType.EXTENDS)
        assert len(edges) >= 1
        # BaseController is in the parse result so should be resolved
        resolved = [e for e in edges if e.resolved]
        assert any("BaseController" in e.target_id for e in resolved)

    def test_unresolved_extends_is_flagged(self):
        """If the supertype is external the edge is marked unresolved."""
        parser = JavalangJavaParser()
        src = "package p; public class Foo extends ExternalBase {}"
        pr = _make_parse_result((src, "Foo.java"))
        g = extract_dependencies(pr)
        extends_edges = [e for e in g.edges if e.relationship == RelationshipType.EXTENDS]
        assert any(not e.resolved for e in extends_edges)

    def test_interface_extends_interface(self):
        g = _graph_from_full()
        # AppRepository extends JpaRepository (external)
        repo_id = "type:com.example.app.repository.AppRepository"
        edges = g.outgoing_edges(repo_id, RelationshipType.EXTENDS)
        assert len(edges) >= 1


# ---------------------------------------------------------------------------
# Relationship: IMPLEMENTS
# ---------------------------------------------------------------------------

class TestImplementsRelationship:
    def test_class_implements_known_interface(self):
        g = _graph_from_full()
        cls_id = "type:com.example.app.AppController"
        edges = g.outgoing_edges(cls_id, RelationshipType.IMPLEMENTS)
        resolved = [e for e in edges if e.resolved]
        target_ids = {e.target_id for e in resolved}
        assert "type:com.example.app.AppApi" in target_ids

    def test_unresolved_implements_flagged(self):
        src = "package p; public class Bar implements ExternalInterface {}"
        pr = _make_parse_result((src, "Bar.java"))
        g = extract_dependencies(pr)
        impl_edges = [e for e in g.edges if e.relationship == RelationshipType.IMPLEMENTS]
        assert any(not e.resolved for e in impl_edges)


# ---------------------------------------------------------------------------
# Relationship: CALLS
# ---------------------------------------------------------------------------

class TestCallsRelationship:
    def test_method_calls_resolved_service_method(self):
        g = _graph_from_full()
        # AppController.listItems -> AppService.fetchItems
        caller = "method:com.example.app.AppController#listItems"
        edges = g.outgoing_edges(caller, RelationshipType.CALLS)
        resolved = [e for e in edges if e.resolved]
        target_ids = {e.target_id for e in resolved}
        assert "method:com.example.app.service.AppService#fetchItems" in target_ids

    def test_method_calls_resolved_repository_method(self):
        g = _graph_from_full()
        # AppService.fetchItems -> AppRepository.findAll (resolved to repo)
        caller = "method:com.example.app.service.AppService#fetchItems"
        edges = g.outgoing_edges(caller, RelationshipType.CALLS)
        resolved = [e for e in edges if e.resolved]
        assert len(resolved) >= 1

    def test_unresolved_calls_flagged(self):
        src = """\
package p;
public class A {
    public void run() {
        ExternalHelper.doSomething();
    }
}
"""
        pr = _make_parse_result((src, "A.java"))
        g = extract_dependencies(pr)
        call_edges = [e for e in g.edges if e.relationship == RelationshipType.CALLS]
        unresolved = [e for e in call_edges if not e.resolved]
        assert len(unresolved) >= 1

    def test_call_edge_metadata(self):
        g = _graph_from_full()
        caller = "method:com.example.app.AppController#listItems"
        edges = g.outgoing_edges(caller, RelationshipType.CALLS)
        assert all("call_name" in e.metadata for e in edges)


# ---------------------------------------------------------------------------
# Relationship: USES
# ---------------------------------------------------------------------------

class TestUsesRelationship:
    def test_controller_uses_service_type(self):
        g = _graph_from_full()
        cls_id = "type:com.example.app.AppController"
        edges = g.outgoing_edges(cls_id, RelationshipType.USES)
        resolved = [e for e in edges if e.resolved]
        target_ids = {e.target_id for e in resolved}
        assert "type:com.example.app.service.AppService" in target_ids

    def test_service_uses_repository_type(self):
        g = _graph_from_full()
        svc_id = "type:com.example.app.service.AppService"
        edges = g.outgoing_edges(svc_id, RelationshipType.USES)
        resolved = [e for e in edges if e.resolved]
        target_ids = {e.target_id for e in resolved}
        assert "type:com.example.app.repository.AppRepository" in target_ids

    def test_jdk_common_types_skipped(self):
        """String, List, Map etc. should not generate USES edges for unresolved nodes."""
        src = """\
package p;
import java.util.List;
public class Foo {
    private String name;
    public List<String> getNames() { return null; }
}
"""
        pr = _make_parse_result((src, "Foo.java"))
        g = extract_dependencies(pr)
        uses_edges = [e for e in g.edges if e.relationship == RelationshipType.USES]
        # No unresolved USES edges should point to String or List
        for e in uses_edges:
            if not e.resolved:
                node = g.get_node(e.target_id)
                assert node is None or node.name not in ("String", "List")


# ---------------------------------------------------------------------------
# Relationship: EXPOSES
# ---------------------------------------------------------------------------

class TestExposesRelationship:
    def test_controller_exposes_endpoint(self):
        g = _graph_from_full()
        cls_id = "type:com.example.app.AppController"
        edges = g.outgoing_edges(cls_id, RelationshipType.EXPOSES)
        assert len(edges) >= 2  # GET /items and POST /items

    def test_method_exposes_endpoint(self):
        g = _graph_from_full()
        m_id = "method:com.example.app.AppController#listItems"
        edges = g.outgoing_edges(m_id, RelationshipType.EXPOSES)
        assert len(edges) >= 1
        assert all(e.resolved for e in edges)

    def test_exposes_target_is_endpoint_node(self):
        g = _graph_from_full()
        cls_id = "type:com.example.app.AppController"
        edges = g.outgoing_edges(cls_id, RelationshipType.EXPOSES)
        for e in edges:
            node = g.get_node(e.target_id)
            assert node is not None
            assert node.kind == "endpoint"


# ---------------------------------------------------------------------------
# Relationship: REFERENCES  (entity → table)
# ---------------------------------------------------------------------------

class TestReferencesRelationship:
    def test_entity_references_table(self):
        g = _graph_from_full()
        entity_id = "type:com.example.app.entity.AppEntity"
        edges = g.outgoing_edges(entity_id, RelationshipType.REFERENCES)
        assert len(edges) >= 1
        target_ids = {e.target_id for e in edges}
        assert "table:app_items" in target_ids

    def test_field_references_column(self):
        g = _graph_from_full()
        field_id = "field:com.example.app.entity.AppEntity.name"
        edges = g.outgoing_edges(field_id, RelationshipType.REFERENCES)
        assert len(edges) >= 1


# ---------------------------------------------------------------------------
# Relationship: QUERIES
# ---------------------------------------------------------------------------

class TestQueriesRelationship:
    def test_repository_queries_entity(self):
        g = _graph_from_full()
        repo_id = "type:com.example.app.repository.AppRepository"
        edges = g.outgoing_edges(repo_id, RelationshipType.QUERIES)
        resolved = [e for e in edges if e.resolved]
        target_ids = {e.target_id for e in resolved}
        assert "type:com.example.app.entity.AppEntity" in target_ids

    def test_repository_queries_table(self):
        g = _graph_from_full()
        repo_id = "type:com.example.app.repository.AppRepository"
        edges = g.outgoing_edges(repo_id, RelationshipType.QUERIES)
        target_ids = {e.target_id for e in edges}
        assert "table:app_items" in target_ids


# ---------------------------------------------------------------------------
# Relationship: DEPENDS_ON
# ---------------------------------------------------------------------------

class TestDependsOnRelationship:
    def test_controller_depends_on_service(self):
        g = _graph_from_full()
        cls_id = "type:com.example.app.AppController"
        edges = g.outgoing_edges(cls_id, RelationshipType.DEPENDS_ON)
        resolved = [e for e in edges if e.resolved]
        target_ids = {e.target_id for e in resolved}
        assert "type:com.example.app.service.AppService" in target_ids

    def test_service_depends_on_repository(self):
        g = _graph_from_full()
        svc_id = "type:com.example.app.service.AppService"
        edges = g.outgoing_edges(svc_id, RelationshipType.DEPENDS_ON)
        resolved = [e for e in edges if e.resolved]
        target_ids = {e.target_id for e in resolved}
        assert "type:com.example.app.repository.AppRepository" in target_ids

    def test_repository_depends_on_table(self):
        g = _graph_from_full()
        repo_id = "type:com.example.app.repository.AppRepository"
        edges = g.outgoing_edges(repo_id, RelationshipType.DEPENDS_ON)
        target_ids = {e.target_id for e in edges}
        assert "table:app_items" in target_ids

    def test_unresolved_external_dependency_flagged(self):
        src = """\
package p;
public class Foo {
    private ExternalDep dep;
}
"""
        pr = _make_parse_result((src, "Foo.java"))
        g = extract_dependencies(pr)
        dep_edges = [e for e in g.edges if e.relationship == RelationshipType.DEPENDS_ON]
        unresolved = [e for e in dep_edges if not e.resolved]
        assert len(unresolved) >= 1


# ---------------------------------------------------------------------------
# Relationship: TESTS
# ---------------------------------------------------------------------------

class TestTestsRelationship:
    def test_test_class_tests_production_class(self):
        g = _graph_from_full()
        test_id = "type:com.example.app.service.AppServiceTest"
        edges = g.outgoing_edges(test_id, RelationshipType.TESTS)
        resolved = [e for e in edges if e.resolved]
        target_ids = {e.target_id for e in resolved}
        assert "type:com.example.app.service.AppService" in target_ids

    def test_test_method_tests_production_method(self):
        g = _graph_from_full()
        test_m_id = "method:com.example.app.service.AppServiceTest#testFetchItems"
        edges = g.outgoing_edges(test_m_id, RelationshipType.TESTS)
        resolved = [e for e in edges if e.resolved]
        target_ids = {e.target_id for e in resolved}
        assert "method:com.example.app.service.AppService#fetchItems" in target_ids

    def test_unresolved_tests_class_flagged(self):
        """If the production class isn't in the parse result, edge is unresolved."""
        src = "package p; public class FooTest { public void testBar() {} }"
        pr = _make_parse_result((src, "FooTest.java"))
        g = extract_dependencies(pr)
        test_edges = [e for e in g.edges if e.relationship == RelationshipType.TESTS]
        unresolved = [e for e in test_edges if not e.resolved]
        assert len(unresolved) >= 1


# ---------------------------------------------------------------------------
# Type resolution unit tests
# ---------------------------------------------------------------------------

class TestTypeResolution:
    def _extractor(self) -> DependencyExtractor:
        return DependencyExtractor(_full_parse_result())

    def test_resolve_by_qualified_name(self):
        ext = self._extractor()
        t, nid, ok = ext.resolve_type("com.example.app.AppController")
        assert ok
        assert t is not None
        assert t.name == "AppController"

    def test_resolve_by_simple_unique_name(self):
        ext = self._extractor()
        t, nid, ok = ext.resolve_type("AppController")
        assert ok
        assert t is not None

    def test_resolve_external_returns_unresolved(self):
        ext = self._extractor()
        t, nid, ok = ext.resolve_type("org.springframework.web.SomeClass")
        assert not ok
        assert t is None

    def test_resolve_via_same_package(self):
        ext = self._extractor()
        # AppApi is in com.example.app; resolve without qualification from same package
        from app.parser.models import ParsedFile
        pf = ParsedFile(file_path="AppController.java", package="com.example.app")
        t, nid, ok = ext.resolve_type("AppApi", pf, "com.example.app")
        assert ok
        assert t is not None
        assert t.name == "AppApi"


# ---------------------------------------------------------------------------
# Graph structure / summary tests
# ---------------------------------------------------------------------------

class TestGraphStructure:
    def test_all_relationship_types_present(self):
        g = _graph_from_full()
        rel_names = {e.relationship for e in g.edges}
        assert RelationshipType.CONTAINS in rel_names
        assert RelationshipType.IMPORTS in rel_names
        assert RelationshipType.EXTENDS in rel_names
        assert RelationshipType.IMPLEMENTS in rel_names
        assert RelationshipType.CALLS in rel_names
        assert RelationshipType.USES in rel_names
        assert RelationshipType.EXPOSES in rel_names
        assert RelationshipType.REFERENCES in rel_names
        assert RelationshipType.QUERIES in rel_names
        assert RelationshipType.DEPENDS_ON in rel_names
        assert RelationshipType.TESTS in rel_names

    def test_graph_has_nodes_and_edges(self):
        g = _graph_from_full()
        assert len(g.nodes) > 10
        assert len(g.edges) > 10

    def test_no_self_edges(self):
        g = _graph_from_full()
        self_edges = [e for e in g.edges if e.source_id == e.target_id]
        assert self_edges == [], f"Found self-referencing edges: {self_edges}"

    def test_summary_line_output(self):
        g = _graph_from_full()
        lines = g.summary_lines()
        assert len(lines) == 2
        assert "nodes" in lines[0]
        assert "resolved" in lines[1]

    def test_extract_dependencies_entry_point(self):
        """extract_dependencies() convenience function works identically to DependencyExtractor.extract()."""
        pr = _full_parse_result()
        g1 = extract_dependencies(pr)
        g2 = DependencyExtractor(pr).extract()
        assert len(g1.nodes) == len(g2.nodes)
        assert len(g1.edges) == len(g2.edges)


# ---------------------------------------------------------------------------
# Integration: payment-service sample project
# ---------------------------------------------------------------------------

class TestPaymentServiceIntegration:
    @pytest.fixture(scope="class")
    def graph(self) -> DependencyGraph:
        assert SAMPLE_ROOT.is_dir(), f"Sample project missing: {SAMPLE_ROOT}"
        pr = parse_repository_java(SAMPLE_ROOT)
        return extract_dependencies(pr)

    def test_graph_is_non_empty(self, graph: DependencyGraph):
        assert len(graph.nodes) > 20
        assert len(graph.edges) > 20

    def test_payment_controller_node_exists(self, graph: DependencyGraph):
        nodes = graph.find_nodes(name="PaymentController")
        assert len(nodes) >= 1
        assert nodes[0].kind == "class"

    def test_payment_service_node_exists(self, graph: DependencyGraph):
        assert len(graph.find_nodes(name="PaymentService")) >= 1

    def test_payment_repository_node_exists(self, graph: DependencyGraph):
        assert len(graph.find_nodes(name="PaymentRepository")) >= 1

    def test_payments_table_node_exists(self, graph: DependencyGraph):
        tables = graph.find_nodes(kind="database_table")
        assert any(t.name == "payments" for t in tables)

    def test_post_api_payment_endpoint_exists(self, graph: DependencyGraph):
        endpoints = graph.find_nodes(kind="endpoint")
        names = {n.name for n in endpoints}
        assert any("/api/payment" in n for n in names)

    def test_controller_depends_on_service(self, graph: DependencyGraph):
        ctrl_nodes = graph.find_nodes(name="PaymentController")
        assert ctrl_nodes
        ctrl_id = ctrl_nodes[0].id
        dep_edges = graph.outgoing_edges(ctrl_id, RelationshipType.DEPENDS_ON)
        target_names = {
            (graph.get_node(e.target_id) or GraphNode("", "unknown", "?")).name
            for e in dep_edges if e.resolved
        }
        assert "PaymentService" in target_names

    def test_service_depends_on_repository(self, graph: DependencyGraph):
        svc_nodes = graph.find_nodes(name="PaymentService")
        assert svc_nodes
        svc_id = svc_nodes[0].id
        dep_edges = graph.outgoing_edges(svc_id, RelationshipType.DEPENDS_ON)
        target_names = {
            (graph.get_node(e.target_id) or GraphNode("", "unknown", "?")).name
            for e in dep_edges if e.resolved
        }
        assert "PaymentRepository" in target_names

    def test_repository_queries_payments_table(self, graph: DependencyGraph):
        repo_nodes = graph.find_nodes(name="PaymentRepository")
        assert repo_nodes
        repo_id = repo_nodes[0].id
        q_edges = graph.outgoing_edges(repo_id, RelationshipType.QUERIES)
        target_ids = {e.target_id for e in q_edges}
        assert "table:payments" in target_ids

    def test_entity_references_payments_table(self, graph: DependencyGraph):
        entity_nodes = graph.find_nodes(name="PaymentEntity")
        assert entity_nodes
        entity_id = entity_nodes[0].id
        ref_edges = graph.outgoing_edges(entity_id, RelationshipType.REFERENCES)
        target_ids = {e.target_id for e in ref_edges}
        assert "table:payments" in target_ids

    def test_controller_exposes_endpoints(self, graph: DependencyGraph):
        ctrl_nodes = graph.find_nodes(name="PaymentController")
        ctrl_id = ctrl_nodes[0].id
        exp_edges = graph.outgoing_edges(ctrl_id, RelationshipType.EXPOSES)
        assert len(exp_edges) >= 1

    def test_test_class_tests_service(self, graph: DependencyGraph):
        test_nodes = graph.find_nodes(name="PaymentServiceTest")
        if not test_nodes:
            pytest.skip("PaymentServiceTest not in parse result")
        test_id = test_nodes[0].id
        t_edges = graph.outgoing_edges(test_id, RelationshipType.TESTS)
        assert len(t_edges) >= 1

    def test_summary_contains_all_key_relationships(self, graph: DependencyGraph):
        summary = graph.summary()
        rel_counts = summary["edges_by_relationship"]
        for rel in (
            "CONTAINS", "IMPORTS", "DEPENDS_ON", "USES", "EXPOSES", "REFERENCES", "QUERIES"
        ):
            assert rel_counts.get(rel, 0) > 0, f"Missing {rel} edges in payment-service graph"

    def test_all_resolved_edges_have_valid_source_and_target(self, graph: DependencyGraph):
        node_ids = {n.id for n in graph.nodes}
        for e in graph.resolved_edges():
            assert e.source_id in node_ids, f"Resolved edge source not a node: {e.source_id}"
            assert e.target_id in node_ids, f"Resolved edge target not a node: {e.target_id}"
