"""Deterministic dependency extraction from parsed Java/Spring code (P3).

Builds a DependencyGraph containing nodes and edges for all 11 relationships
specified in PLAN.md:
  - CONTAINS
  - IMPORTS
  - EXTENDS
  - IMPLEMENTS
  - CALLS
  - USES
  - EXPOSES
  - QUERIES
  - DEPENDS_ON
  - REFERENCES
  - TESTS

Deterministic evidence only; no LLM. Unresolved relationships are explicitly
flagged with resolved=False.
"""

from __future__ import annotations

import re
from typing import Any

from app.graph.models import DependencyGraph, GraphEdge, GraphNode, RelationshipType
from app.parser.models import (
    DatabaseReference,
    EndpointInfo,
    FieldInfo,
    ImportInfo,
    MethodCallInfo,
    MethodInfo,
    ParsedFile,
    ParseResult,
    TypeInfo,
)

PRIMITIVE_TYPES = frozenset(
    {
        "void",
        "int",
        "long",
        "boolean",
        "double",
        "float",
        "byte",
        "short",
        "char",
    }
)

JDK_COMMON_TYPES = frozenset(
    {
        "String",
        "Object",
        "Class",
        "Integer",
        "Long",
        "Boolean",
        "Double",
        "Float",
        "Byte",
        "Short",
        "Character",
        "BigDecimal",
        "BigInteger",
        "Instant",
        "LocalDate",
        "LocalDateTime",
        "List",
        "Map",
        "Set",
        "Collection",
        "Optional",
        "Void",
    }
)


def strip_generics_and_arrays(type_str: str) -> str:
    """Return the raw type name without generics or array brackets."""
    if not type_str:
        return ""
    cleaned = type_str.strip()
    if "<" in cleaned:
        cleaned = cleaned[: cleaned.index("<")].strip()
    cleaned = re.sub(r"\[\s*\]", "", cleaned).strip()
    return cleaned


def extract_all_type_tokens(type_str: str) -> list[str]:
    """Extract all individual type tokens from a complex type string (e.g. Map<String, List<PaymentEntity>>)."""
    if not type_str:
        return []
    # Match Java identifier patterns
    tokens = re.findall(r"\b[A-Z][a-zA-Z0-9_]*\b", type_str)
    return [t for t in tokens if t not in PRIMITIVE_TYPES]


def extract_generic_arguments(type_str: str) -> list[str]:
    """Extract first-level generic type arguments from a type string."""
    if not type_str or "<" not in type_str:
        return []
    start = type_str.find("<")
    end = type_str.rfind(">")
    if start == -1 or end == -1 or start >= end:
        return []
    inside = type_str[start + 1 : end]
    parts: list[str] = []
    depth = 0
    curr: list[str] = []
    for ch in inside:
        if ch == "<":
            depth += 1
            curr.append(ch)
        elif ch == ">":
            depth -= 1
            curr.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(curr).strip())
            curr = []
        else:
            curr.append(ch)
    if curr:
        parts.append("".join(curr).strip())
    return [strip_generics_and_arrays(p) for p in parts if p]


class DependencyExtractor:
    """Extracts software dependency graphs from parsed Java/Spring metadata."""

    def __init__(self, parse_result: ParseResult) -> None:
        self.parse_result = parse_result
        self.graph = DependencyGraph()

        # Indexes for fast deterministic lookup
        self.types_by_qname: dict[str, TypeInfo] = {}
        self.types_by_simple_name: dict[str, list[TypeInfo]] = {}
        self.file_by_type_qname: dict[str, ParsedFile] = {}
        self.methods_by_type: dict[str, dict[str, list[MethodInfo]]] = {}
        self.fields_by_type: dict[str, dict[str, FieldInfo]] = {}

        # Database mapping: entity class -> table name, entity field -> column name
        self.table_by_entity: dict[str, str] = {}
        self.columns_by_table: dict[str, set[str]] = {}

        self._build_indexes()

    def _build_indexes(self) -> None:
        for pf in self.parse_result.files:
            for t in pf.types:
                self._index_type(t, pf)

        for db_ref in self.parse_result.database_references:
            if db_ref.kind == "table":
                self.table_by_entity[db_ref.owning_type] = db_ref.name
                if db_ref.name not in self.columns_by_table:
                    self.columns_by_table[db_ref.name] = set()
            elif db_ref.kind == "column":
                table_name = self.table_by_entity.get(db_ref.owning_type)
                if table_name:
                    self.columns_by_table.setdefault(table_name, set()).add(db_ref.name)

    def _index_type(self, t: TypeInfo, pf: ParsedFile) -> None:
        self.types_by_qname[t.qualified_name] = t
        self.types_by_simple_name.setdefault(t.name, []).append(t)
        self.file_by_type_qname[t.qualified_name] = pf

        methods_dict: dict[str, list[MethodInfo]] = {}
        for m in t.methods + t.constructors:
            methods_dict.setdefault(m.name, []).append(m)
        self.methods_by_type[t.qualified_name] = methods_dict

        fields_dict: dict[str, FieldInfo] = {}
        for f in t.fields:
            fields_dict[f.name] = f
        self.fields_by_type[t.qualified_name] = fields_dict

        for nested in t.nested_types:
            self._index_type(nested, pf)

    # ------------------------------------------------------------------
    # ID Conventions
    # ------------------------------------------------------------------
    @staticmethod
    def type_id(qualified_name: str) -> str:
        return f"type:{qualified_name}"

    @staticmethod
    def method_id(type_qname: str, method_name: str) -> str:
        return f"method:{type_qname}#{method_name}"

    @staticmethod
    def field_id(type_qname: str, field_name: str) -> str:
        return f"field:{type_qname}.{field_name}"

    @staticmethod
    def package_id(pkg_name: str) -> str:
        return f"package:{pkg_name}"

    @staticmethod
    def file_id(file_path: str) -> str:
        return f"file:{file_path}"

    @staticmethod
    def endpoint_id(http_method: str, path: str) -> str:
        return f"endpoint:{http_method.upper()}:{path}"

    @staticmethod
    def table_id(table_name: str) -> str:
        return f"table:{table_name}"

    @staticmethod
    def column_id(table_name: str, column_name: str) -> str:
        return f"column:{table_name}.{column_name}"

    @staticmethod
    def unresolved_id(name: str) -> str:
        return f"unresolved:{name}"

    # ------------------------------------------------------------------
    # Symbol Resolution
    # ------------------------------------------------------------------
    def resolve_type(
        self,
        raw_name: str,
        context_file: ParsedFile | None = None,
        context_pkg: str | None = None,
    ) -> tuple[TypeInfo | None, str, bool]:
        """
        Deterministically resolve a type reference within the repository.
        Returns: (resolved_type_info_or_none, canonical_name_or_id, is_resolved)
        """
        clean = strip_generics_and_arrays(raw_name)
        if not clean:
            return None, "", False

        # 1. Exact match on qualified name
        if clean in self.types_by_qname:
            return self.types_by_qname[clean], self.type_id(clean), True

        # 2. Check context file imports
        if context_file:
            for imp in context_file.imports:
                if not imp.is_wildcard:
                    if imp.path.endswith(f".{clean}") or imp.path == clean:
                        if imp.path in self.types_by_qname:
                            return self.types_by_qname[imp.path], self.type_id(imp.path), True
                        # Explicit import to external library
                        return None, self.unresolved_id(imp.path), False

            # Check same package
            pkg = context_file.package or context_pkg
            if pkg:
                qname = f"{pkg}.{clean}"
                if qname in self.types_by_qname:
                    return self.types_by_qname[qname], self.type_id(qname), True

            # Check wildcard imports against known types
            for imp in context_file.imports:
                if imp.is_wildcard:
                    base_pkg = imp.path.rstrip(".*")
                    qname = f"{base_pkg}.{clean}"
                    if qname in self.types_by_qname:
                        return self.types_by_qname[qname], self.type_id(qname), True

        elif context_pkg:
            qname = f"{context_pkg}.{clean}"
            if qname in self.types_by_qname:
                return self.types_by_qname[qname], self.type_id(qname), True

        # 3. Project-wide unique simple name match
        if clean in self.types_by_simple_name:
            candidates = self.types_by_simple_name[clean]
            if len(candidates) == 1:
                t = candidates[0]
                return t, self.type_id(t.qualified_name), True

        # 4. External or unresolved type
        return None, self.unresolved_id(clean), False

    # ------------------------------------------------------------------
    # Extraction Pipeline
    # ------------------------------------------------------------------
    def extract(self) -> DependencyGraph:
        """Run complete extraction across all parsed code."""
        self._create_base_nodes()
        self._extract_contains()
        self._extract_imports()
        self._extract_extends_and_implements()
        self._extract_uses()
        self._extract_calls()
        self._extract_exposes()
        self._extract_database_references_and_queries()
        self._extract_depends_on()
        self._extract_tests()
        return self.graph

    def _create_base_nodes(self) -> None:
        """Create primary GraphNode entities for packages, files, types, methods, fields, tables, endpoints."""
        # Packages
        for pkg in self.parse_result.packages:
            self.graph.add_node(
                GraphNode(
                    id=self.package_id(pkg),
                    kind="package",
                    name=pkg,
                    qualified_name=pkg,
                )
            )

        # Files
        for pf in self.parse_result.files:
            self.graph.add_node(
                GraphNode(
                    id=self.file_id(pf.file_path),
                    kind="file",
                    name=pf.file_path.rsplit("/", 1)[-1],
                    file_path=pf.file_path,
                )
            )

        # Types, methods, fields
        for t in self.types_by_qname.values():
            self._create_type_nodes(t)

        # Endpoints
        for ep in self.parse_result.endpoints:
            ep_id = self.endpoint_id(ep.http_method, ep.path)
            self.graph.add_node(
                GraphNode(
                    id=ep_id,
                    kind="endpoint",
                    name=f"{ep.http_method} {ep.path}",
                    qualified_name=f"{ep.http_method} {ep.path}",
                    file_path=ep.source.file_path if ep.source else None,
                    metadata={
                        "http_method": ep.http_method,
                        "path": ep.path,
                        "handler_class": ep.handler_class,
                        "handler_method": ep.handler_method,
                    },
                )
            )

        # Database tables & columns
        for db_ref in self.parse_result.database_references:
            if db_ref.kind == "table":
                t_id = self.table_id(db_ref.name)
                self.graph.add_node(
                    GraphNode(
                        id=t_id,
                        kind="database_table",
                        name=db_ref.name,
                        qualified_name=db_ref.name,
                        file_path=db_ref.source.file_path if db_ref.source else None,
                        metadata={"owning_type": db_ref.owning_type},
                    )
                )
            elif db_ref.kind == "column":
                table_name = self.table_by_entity.get(db_ref.owning_type, "unknown_table")
                c_id = self.column_id(table_name, db_ref.name)
                self.graph.add_node(
                    GraphNode(
                        id=c_id,
                        kind="database_column",
                        name=db_ref.name,
                        qualified_name=f"{table_name}.{db_ref.name}",
                        file_path=db_ref.source.file_path if db_ref.source else None,
                        metadata={"table": table_name, "owning_type": db_ref.owning_type},
                    )
                )

    def _create_type_nodes(self, t: TypeInfo) -> None:
        t_id = self.type_id(t.qualified_name)
        self.graph.add_node(
            GraphNode(
                id=t_id,
                kind=t.kind,
                name=t.name,
                qualified_name=t.qualified_name,
                file_path=t.source.file_path if t.source else None,
                metadata={
                    "package": t.package,
                    "modifiers": t.modifiers,
                    "annotations": [a.name for a in t.annotations],
                    "extends": t.extends,
                    "implements": t.implements,
                },
            )
        )

        # Fields
        for f in t.fields:
            f_id = self.field_id(t.qualified_name, f.name)
            self.graph.add_node(
                GraphNode(
                    id=f_id,
                    kind="field",
                    name=f.name,
                    qualified_name=f"{t.qualified_name}.{f.name}",
                    file_path=f.source.file_path if f.source else (t.source.file_path if t.source else None),
                    metadata={"type_name": f.type_name, "modifiers": f.modifiers},
                )
            )

        # Methods & Constructors
        for m in t.methods + t.constructors:
            m_id = self.method_id(t.qualified_name, m.name)
            self.graph.add_node(
                GraphNode(
                    id=m_id,
                    kind="method",
                    name=m.name,
                    qualified_name=f"{t.qualified_name}#{m.name}",
                    file_path=m.source.file_path if m.source else (t.source.file_path if t.source else None),
                    metadata={
                        "return_type": m.return_type,
                        "modifiers": m.modifiers,
                        "is_constructor": m.is_constructor,
                        "parameters": [{"name": p.name, "type": p.type_name} for p in m.parameters],
                        "signature": m.signature,
                    },
                )
            )

        for nested in t.nested_types:
            self._create_type_nodes(nested)

    # ------------------------------------------------------------------
    # 1. CONTAINS
    # ------------------------------------------------------------------
    def _extract_contains(self) -> None:
        for pf in self.parse_result.files:
            file_nid = self.file_id(pf.file_path)

            for t in pf.types:
                t_nid = self.type_id(t.qualified_name)
                # File CONTAINS Type
                self.graph.add_edge(
                    GraphEdge(
                        source_id=file_nid,
                        target_id=t_nid,
                        relationship=RelationshipType.CONTAINS,
                        resolved=True,
                    )
                )

                # Package CONTAINS Type
                if t.package:
                    pkg_nid = self.package_id(t.package)
                    self.graph.add_edge(
                        GraphEdge(
                            source_id=pkg_nid,
                            target_id=t_nid,
                            relationship=RelationshipType.CONTAINS,
                            resolved=True,
                        )
                    )

                self._extract_type_contains(t)

        # Table CONTAINS Column
        for table_name, columns in self.columns_by_table.items():
            tbl_id = self.table_id(table_name)
            for col in columns:
                col_id = self.column_id(table_name, col)
                self.graph.add_edge(
                    GraphEdge(
                        source_id=tbl_id,
                        target_id=col_id,
                        relationship=RelationshipType.CONTAINS,
                        resolved=True,
                    )
                )

    def _extract_type_contains(self, t: TypeInfo) -> None:
        t_nid = self.type_id(t.qualified_name)
        for f in t.fields:
            self.graph.add_edge(
                GraphEdge(
                    source_id=t_nid,
                    target_id=self.field_id(t.qualified_name, f.name),
                    relationship=RelationshipType.CONTAINS,
                    resolved=True,
                )
            )
        for m in t.methods + t.constructors:
            self.graph.add_edge(
                GraphEdge(
                    source_id=t_nid,
                    target_id=self.method_id(t.qualified_name, m.name),
                    relationship=RelationshipType.CONTAINS,
                    resolved=True,
                )
            )
        for nested in t.nested_types:
            nested_id = self.type_id(nested.qualified_name)
            self.graph.add_edge(
                GraphEdge(
                    source_id=t_nid,
                    target_id=nested_id,
                    relationship=RelationshipType.CONTAINS,
                    resolved=True,
                )
            )
            self._extract_type_contains(nested)

    # ------------------------------------------------------------------
    # 2. IMPORTS
    # ------------------------------------------------------------------
    def _extract_imports(self) -> None:
        for pf in self.parse_result.files:
            file_nid = self.file_id(pf.file_path)
            for imp in pf.imports:
                target_type, target_id, is_resolved = self.resolve_type(imp.path, pf)
                if not is_resolved:
                    target_id = self.unresolved_id(imp.path)
                    self.graph.add_node(
                        GraphNode(
                            id=target_id,
                            kind="class",
                            name=imp.path.rsplit(".", 1)[-1],
                            qualified_name=imp.path,
                            metadata={"external": True},
                        )
                    )

                # Edge from file
                self.graph.add_edge(
                    GraphEdge(
                        source_id=file_nid,
                        target_id=target_id,
                        relationship=RelationshipType.IMPORTS,
                        resolved=is_resolved,
                        metadata={"import_path": imp.path, "is_static": imp.is_static},
                    )
                )

                # Also edge from each top-level type in the file
                for t in pf.types:
                    self.graph.add_edge(
                        GraphEdge(
                            source_id=self.type_id(t.qualified_name),
                            target_id=target_id,
                            relationship=RelationshipType.IMPORTS,
                            resolved=is_resolved,
                            metadata={"import_path": imp.path},
                        )
                    )

    # ------------------------------------------------------------------
    # 3 & 4. EXTENDS & IMPLEMENTS
    # ------------------------------------------------------------------
    def _extract_extends_and_implements(self) -> None:
        for t in self.types_by_qname.values():
            pf = self.file_by_type_qname.get(t.qualified_name)
            t_nid = self.type_id(t.qualified_name)

            # EXTENDS
            for super_name in t.extends:
                target_type, target_id, is_resolved = self.resolve_type(super_name, pf, t.package)
                if not is_resolved:
                    target_id = self.unresolved_id(super_name)
                    self.graph.add_node(
                        GraphNode(
                            id=target_id,
                            kind="class" if t.kind != "interface" else "interface",
                            name=super_name,
                            qualified_name=super_name,
                            metadata={"external": True},
                        )
                    )
                self.graph.add_edge(
                    GraphEdge(
                        source_id=t_nid,
                        target_id=target_id,
                        relationship=RelationshipType.EXTENDS,
                        resolved=is_resolved,
                        metadata={"super_type": super_name},
                    )
                )

            # IMPLEMENTS
            for iface_name in t.implements:
                target_type, target_id, is_resolved = self.resolve_type(iface_name, pf, t.package)
                if not is_resolved:
                    target_id = self.unresolved_id(iface_name)
                    self.graph.add_node(
                        GraphNode(
                            id=target_id,
                            kind="interface",
                            name=iface_name,
                            qualified_name=iface_name,
                            metadata={"external": True},
                        )
                    )
                self.graph.add_edge(
                    GraphEdge(
                        source_id=t_nid,
                        target_id=target_id,
                        relationship=RelationshipType.IMPLEMENTS,
                        resolved=is_resolved,
                        metadata={"interface": iface_name},
                    )
                )

    # ------------------------------------------------------------------
    # 5. CALLS
    # ------------------------------------------------------------------
    def _extract_calls(self) -> None:
        for t in self.types_by_qname.values():
            pf = self.file_by_type_qname.get(t.qualified_name)

            # Map fields in this type to their raw type names
            field_types: dict[str, str] = {
                f.name: strip_generics_and_arrays(f.type_name) for f in t.fields
            }

            for m in t.methods + t.constructors:
                caller_mid = self.method_id(t.qualified_name, m.name)

                # Local parameter types in this method
                param_types: dict[str, str] = {
                    p.name: strip_generics_and_arrays(p.type_name) for p in m.parameters
                }

                for call in m.method_calls:
                    target_mid, is_resolved = self._resolve_method_call(
                        call=call,
                        enclosing_type=t,
                        enclosing_method=m,
                        field_types=field_types,
                        param_types=param_types,
                        pf=pf,
                    )

                    if not is_resolved:
                        call_label = (
                            f"{call.qualifier}.{call.name}" if call.qualifier else call.name
                        )
                        target_mid = self.unresolved_id(call_label)
                        self.graph.add_node(
                            GraphNode(
                                id=target_mid,
                                kind="method",
                                name=call.name,
                                qualified_name=call_label,
                                metadata={"unresolved": True},
                            )
                        )

                    self.graph.add_edge(
                        GraphEdge(
                            source_id=caller_mid,
                            target_id=target_mid,
                            relationship=RelationshipType.CALLS,
                            resolved=is_resolved,
                            metadata={"call_name": call.name, "qualifier": call.qualifier},
                        )
                    )

    def _resolve_method_call(
        self,
        call: MethodCallInfo,
        enclosing_type: TypeInfo,
        enclosing_method: MethodInfo,
        field_types: dict[str, str],
        param_types: dict[str, str],
        pf: ParsedFile | None,
    ) -> tuple[str, bool]:
        """Try resolving a method invocation to a target method node in the repository."""
        # 1. Calls on this / self / super or without qualifier (same class or hierarchy)
        if call.qualifier in (None, "", "this", "self"):
            if call.name in self.methods_by_type.get(enclosing_type.qualified_name, {}):
                return self.method_id(enclosing_type.qualified_name, call.name), True
            # Check superclasses / interfaces
            for super_name in enclosing_type.extends + enclosing_type.implements:
                target_type, _, is_res = self.resolve_type(super_name, pf, enclosing_type.package)
                if is_res and target_type and call.name in self.methods_by_type.get(target_type.qualified_name, {}):
                    return self.method_id(target_type.qualified_name, call.name), True

        # 2. Calls on fields of enclosing type (e.g. paymentService.processPayment)
        if call.qualifier and call.qualifier in field_types:
            ftype_name = field_types[call.qualifier]
            target_type, _, is_res = self.resolve_type(ftype_name, pf, enclosing_type.package)
            if is_res and target_type:
                m_id = self.method_id(target_type.qualified_name, call.name)
                # Ensure the method node exists (may be inherited, e.g. JpaRepository.save)
                if not self.graph.get_node(m_id):
                    self.graph.add_node(
                        GraphNode(
                            id=m_id,
                            kind="method",
                            name=call.name,
                            qualified_name=f"{target_type.qualified_name}#{call.name}",
                            file_path=target_type.source.file_path if target_type.source else None,
                            metadata={"inherited": True},
                        )
                    )
                return m_id, True

        # 3. Calls on method parameters (e.g. payment.getId())
        if call.qualifier and call.qualifier in param_types:
            ptype_name = param_types[call.qualifier]
            target_type, _, is_res = self.resolve_type(ptype_name, pf, enclosing_type.package)
            if is_res and target_type:
                m_id = self.method_id(target_type.qualified_name, call.name)
                if not self.graph.get_node(m_id):
                    self.graph.add_node(
                        GraphNode(
                            id=m_id,
                            kind="method",
                            name=call.name,
                            qualified_name=f"{target_type.qualified_name}#{call.name}",
                            file_path=target_type.source.file_path if target_type.source else None,
                            metadata={"inherited": True},
                        )
                    )
                return m_id, True

        # 4. Static call on a known class name (e.g. PaymentService.someStatic())
        if call.qualifier:
            target_type, _, is_res = self.resolve_type(call.qualifier, pf, enclosing_type.package)
            if is_res and target_type:
                m_id = self.method_id(target_type.qualified_name, call.name)
                if not self.graph.get_node(m_id):
                    self.graph.add_node(
                        GraphNode(
                            id=m_id,
                            kind="method",
                            name=call.name,
                            qualified_name=f"{target_type.qualified_name}#{call.name}",
                            file_path=target_type.source.file_path if target_type.source else None,
                            metadata={"inherited": True},
                        )
                    )
                return m_id, True

        return "", False

    # ------------------------------------------------------------------
    # 6. USES
    # ------------------------------------------------------------------
    def _extract_uses(self) -> None:
        for t in self.types_by_qname.values():
            pf = self.file_by_type_qname.get(t.qualified_name)
            t_nid = self.type_id(t.qualified_name)

            tokens: set[str] = set()

            for f in t.fields:
                tokens.update(extract_all_type_tokens(f.type_name))

            for m in t.methods + t.constructors:
                if m.return_type:
                    tokens.update(extract_all_type_tokens(m.return_type))
                for p in m.parameters:
                    tokens.update(extract_all_type_tokens(p.type_name))

            for raw_t in tokens:
                if raw_t == t.name:
                    continue  # skip self
                target_type, target_id, is_resolved = self.resolve_type(raw_t, pf, t.package)
                if not is_resolved:
                    # Do not flood with common JDK primitives/built-ins if not desirable,
                    # but create unresolved node with resolved=False
                    if raw_t in JDK_COMMON_TYPES:
                        continue
                    target_id = self.unresolved_id(raw_t)
                    self.graph.add_node(
                        GraphNode(
                            id=target_id,
                            kind="class",
                            name=raw_t,
                            qualified_name=raw_t,
                            metadata={"external": True},
                        )
                    )

                self.graph.add_edge(
                    GraphEdge(
                        source_id=t_nid,
                        target_id=target_id,
                        relationship=RelationshipType.USES,
                        resolved=is_resolved,
                        metadata={"type_token": raw_t},
                    )
                )

    # ------------------------------------------------------------------
    # 7. EXPOSES
    # ------------------------------------------------------------------
    def _extract_exposes(self) -> None:
        for ep in self.parse_result.endpoints:
            ep_id = self.endpoint_id(ep.http_method, ep.path)

            # Handler Class EXPOSES Endpoint
            target_type, type_id, is_resolved = self.resolve_type(ep.handler_class)
            if is_resolved and target_type:
                self.graph.add_edge(
                    GraphEdge(
                        source_id=type_id,
                        target_id=ep_id,
                        relationship=RelationshipType.EXPOSES,
                        resolved=True,
                    )
                )

                # Handler Method EXPOSES Endpoint
                m_id = self.method_id(target_type.qualified_name, ep.handler_method)
                self.graph.add_edge(
                    GraphEdge(
                        source_id=m_id,
                        target_id=ep_id,
                        relationship=RelationshipType.EXPOSES,
                        resolved=True,
                    )
                )

    # ------------------------------------------------------------------
    # 8 & 10. DATABASE REFERENCES & QUERIES
    # ------------------------------------------------------------------
    def _extract_database_references_and_queries(self) -> None:
        # Entity REFERENCES Table
        for db_ref in self.parse_result.database_references:
            if db_ref.kind == "table":
                entity_type, entity_id, is_res = self.resolve_type(db_ref.owning_type)
                tbl_id = self.table_id(db_ref.name)
                source_id = entity_id if is_res else self.unresolved_id(db_ref.owning_type)
                self.graph.add_edge(
                    GraphEdge(
                        source_id=source_id,
                        target_id=tbl_id,
                        relationship=RelationshipType.REFERENCES,
                        resolved=is_res,
                        metadata={"table": db_ref.name},
                    )
                )
            elif db_ref.kind == "column":
                table_name = self.table_by_entity.get(db_ref.owning_type, "unknown_table")
                col_id = self.column_id(table_name, db_ref.name)
                # Find field in owning type — details key is "field" (Java field name)
                entity_type, _, is_res = self.resolve_type(db_ref.owning_type)
                if is_res and entity_type:
                    field_name = db_ref.details.get("field") or db_ref.details.get("field_name") or db_ref.name
                    f_id = self.field_id(entity_type.qualified_name, field_name)
                    # Only create the REFERENCES edge if the field node exists
                    if self.graph.get_node(f_id):
                        self.graph.add_edge(
                            GraphEdge(
                                source_id=f_id,
                                target_id=col_id,
                                relationship=RelationshipType.REFERENCES,
                                resolved=True,
                                metadata={"column": db_ref.name, "table": table_name},
                            )
                        )

        # Repositories QUERIES Entity and Table
        for t in self.types_by_qname.values():
            is_repo = any(
                ann.name in ("Repository", "org.springframework.stereotype.Repository")
                for ann in t.annotations
            )
            # Check if extends JpaRepository or CrudRepository
            for super_type in t.extends:
                if any(k in super_type for k in ("Repository", "JpaRepository", "CrudRepository")):
                    is_repo = True
                    type_args = extract_generic_arguments(super_type)
                    if type_args:
                        entity_name = type_args[0]
                        pf = self.file_by_type_qname.get(t.qualified_name)
                        ent_type, ent_id, ent_resolved = self.resolve_type(entity_name, pf, t.package)
                        if ent_resolved and ent_type:
                            # Repository QUERIES Entity
                            self.graph.add_edge(
                                GraphEdge(
                                    source_id=self.type_id(t.qualified_name),
                                    target_id=ent_id,
                                    relationship=RelationshipType.QUERIES,
                                    resolved=True,
                                    metadata={"entity": ent_type.name},
                                )
                            )
                            # Repository QUERIES Table — look up by qualified name
                            tbl_name = self.table_by_entity.get(ent_type.qualified_name)
                            if tbl_name:
                                self.graph.add_edge(
                                    GraphEdge(
                                        source_id=self.type_id(t.qualified_name),
                                        target_id=self.table_id(tbl_name),
                                        relationship=RelationshipType.QUERIES,
                                        resolved=True,
                                        metadata={"table": tbl_name},
                                    )
                                )

    # ------------------------------------------------------------------
    # 9. DEPENDS_ON
    # ------------------------------------------------------------------
    def _extract_depends_on(self) -> None:
        """
        Extract architectural component dependencies.
        E.g. PaymentController -> PaymentService -> PaymentRepository -> payments
        """
        for t in self.types_by_qname.values():
            pf = self.file_by_type_qname.get(t.qualified_name)
            t_nid = self.type_id(t.qualified_name)

            # Component dependencies via injected fields or constructor arguments
            candidate_deps: set[str] = set()

            for f in t.fields:
                clean_type = strip_generics_and_arrays(f.type_name)
                if clean_type and clean_type not in PRIMITIVE_TYPES and clean_type not in JDK_COMMON_TYPES:
                    candidate_deps.add(clean_type)

            for c in t.constructors:
                for p in c.parameters:
                    clean_type = strip_generics_and_arrays(p.type_name)
                    if clean_type and clean_type not in PRIMITIVE_TYPES and clean_type not in JDK_COMMON_TYPES:
                        candidate_deps.add(clean_type)

            for dep_name in candidate_deps:
                target_type, target_id, is_resolved = self.resolve_type(dep_name, pf, t.package)
                if is_resolved and target_type and target_type.qualified_name != t.qualified_name:
                    self.graph.add_edge(
                        GraphEdge(
                            source_id=t_nid,
                            target_id=target_id,
                            relationship=RelationshipType.DEPENDS_ON,
                            resolved=True,
                            metadata={"dependency_type": dep_name},
                        )
                    )
                elif not is_resolved and dep_name:
                    target_id = self.unresolved_id(dep_name)
                    self.graph.add_node(
                        GraphNode(
                            id=target_id,
                            kind="class",
                            name=dep_name,
                            qualified_name=dep_name,
                            metadata={"external": True},
                        )
                    )
                    self.graph.add_edge(
                        GraphEdge(
                            source_id=t_nid,
                            target_id=target_id,
                            relationship=RelationshipType.DEPENDS_ON,
                            resolved=False,
                            metadata={"dependency_type": dep_name},
                        )
                    )

            # Repository DEPENDS_ON database table
            for super_type in t.extends:
                if any(k in super_type for k in ("Repository", "JpaRepository", "CrudRepository")):
                    type_args = extract_generic_arguments(super_type)
                    if type_args:
                        entity_name = type_args[0]
                        pf = self.file_by_type_qname.get(t.qualified_name)
                        ent_type, _, ent_res = self.resolve_type(entity_name, pf, t.package)
                        tbl_name = self.table_by_entity.get(ent_type.qualified_name) if ent_res and ent_type else None
                        if tbl_name:
                            self.graph.add_edge(
                                GraphEdge(
                                    source_id=t_nid,
                                    target_id=self.table_id(tbl_name),
                                    relationship=RelationshipType.DEPENDS_ON,
                                    resolved=True,
                                    metadata={"table": tbl_name},
                                )
                            )

    # ------------------------------------------------------------------
    # 11. TESTS
    # ------------------------------------------------------------------
    def _extract_tests(self) -> None:
        """
        Identify test classes and link them to the target production classes/methods being tested.
        """
        for t in self.types_by_qname.values():
            pf = self.file_by_type_qname.get(t.qualified_name)
            is_test_file = pf and ("src/test" in pf.file_path or "Test.java" in pf.file_path)
            is_test_class = (
                is_test_file
                or t.name.endswith("Test")
                or t.name.endswith("Tests")
                or any("Test" in a.name for a in t.annotations)
            )

            if not is_test_class:
                continue

            test_nid = self.type_id(t.qualified_name)

            # 1. Convention: PaymentServiceTest -> PaymentService
            tested_class_name = re.sub(r"(Test|Tests|TestCase)$", "", t.name)
            target_type, target_id, is_resolved = self.resolve_type(tested_class_name, pf, t.package)

            if is_resolved and target_type and target_type.qualified_name != t.qualified_name:
                self.graph.add_edge(
                    GraphEdge(
                        source_id=test_nid,
                        target_id=target_id,
                        relationship=RelationshipType.TESTS,
                        resolved=True,
                        metadata={"target_class": target_type.name},
                    )
                )

                # Link test methods to tested methods called inside them
                for tm in t.methods:
                    test_m_nid = self.method_id(t.qualified_name, tm.name)
                    for call in tm.method_calls:
                        if call.name in self.methods_by_type.get(target_type.qualified_name, {}):
                            target_m_nid = self.method_id(target_type.qualified_name, call.name)
                            self.graph.add_edge(
                                GraphEdge(
                                    source_id=test_m_nid,
                                    target_id=target_m_nid,
                                    relationship=RelationshipType.TESTS,
                                    resolved=True,
                                    metadata={"target_method": call.name},
                                )
                            )
            elif tested_class_name and tested_class_name != t.name:
                # Target class could not be resolved in the repo
                target_id = self.unresolved_id(tested_class_name)
                self.graph.add_node(
                    GraphNode(
                        id=target_id,
                        kind="class",
                        name=tested_class_name,
                        qualified_name=tested_class_name,
                        metadata={"unresolved": True},
                    )
                )
                self.graph.add_edge(
                    GraphEdge(
                        source_id=test_nid,
                        target_id=target_id,
                        relationship=RelationshipType.TESTS,
                        resolved=False,
                        metadata={"target_class": tested_class_name},
                    )
                )


def extract_dependencies(parse_result: ParseResult) -> DependencyGraph:
    """Convenience entry point for building a DependencyGraph from a ParseResult."""
    return DependencyExtractor(parse_result).extract()
