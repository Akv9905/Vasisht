"""Structured metadata extracted from Java source (deterministic; no LLM)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


TypeKind = Literal["class", "interface", "enum", "annotation", "record", "unknown"]


@dataclass
class SourceRef:
    """Source-file location for an extracted entity."""

    file_path: str
    start_line: int | None = None
    end_line: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AnnotationInfo:
    name: str
    arguments: dict[str, str] = field(default_factory=dict)
    source: SourceRef | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "arguments": self.arguments,
            "source": self.source.to_dict() if self.source else None,
        }


@dataclass
class ImportInfo:
    path: str
    is_static: bool = False
    is_wildcard: bool = False
    source: SourceRef | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "is_static": self.is_static,
            "is_wildcard": self.is_wildcard,
            "source": self.source.to_dict() if self.source else None,
        }


@dataclass
class FieldInfo:
    name: str
    type_name: str
    modifiers: list[str] = field(default_factory=list)
    annotations: list[AnnotationInfo] = field(default_factory=list)
    source: SourceRef | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type_name": self.type_name,
            "modifiers": self.modifiers,
            "annotations": [a.to_dict() for a in self.annotations],
            "source": self.source.to_dict() if self.source else None,
        }


@dataclass
class ParameterInfo:
    name: str
    type_name: str
    annotations: list[AnnotationInfo] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type_name": self.type_name,
            "annotations": [a.to_dict() for a in self.annotations],
        }


@dataclass
class MethodCallInfo:
    """A method invocation found in a method/constructor body."""

    name: str
    qualifier: str | None = None
    source: SourceRef | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "qualifier": self.qualifier,
            "source": self.source.to_dict() if self.source else None,
        }


@dataclass
class MethodInfo:
    name: str
    return_type: str | None
    parameters: list[ParameterInfo] = field(default_factory=list)
    modifiers: list[str] = field(default_factory=list)
    annotations: list[AnnotationInfo] = field(default_factory=list)
    throws: list[str] = field(default_factory=list)
    is_constructor: bool = False
    method_calls: list[MethodCallInfo] = field(default_factory=list)
    signature: str = ""
    source: SourceRef | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "return_type": self.return_type,
            "parameters": [p.to_dict() for p in self.parameters],
            "modifiers": self.modifiers,
            "annotations": [a.to_dict() for a in self.annotations],
            "throws": self.throws,
            "is_constructor": self.is_constructor,
            "method_calls": [c.to_dict() for c in self.method_calls],
            "signature": self.signature,
            "source": self.source.to_dict() if self.source else None,
        }


@dataclass
class TypeInfo:
    name: str
    kind: TypeKind
    package: str | None
    qualified_name: str
    modifiers: list[str] = field(default_factory=list)
    annotations: list[AnnotationInfo] = field(default_factory=list)
    extends: list[str] = field(default_factory=list)
    implements: list[str] = field(default_factory=list)
    fields: list[FieldInfo] = field(default_factory=list)
    methods: list[MethodInfo] = field(default_factory=list)
    constructors: list[MethodInfo] = field(default_factory=list)
    nested_types: list[TypeInfo] = field(default_factory=list)
    source: SourceRef | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "package": self.package,
            "qualified_name": self.qualified_name,
            "modifiers": self.modifiers,
            "annotations": [a.to_dict() for a in self.annotations],
            "extends": self.extends,
            "implements": self.implements,
            "fields": [f.to_dict() for f in self.fields],
            "methods": [m.to_dict() for m in self.methods],
            "constructors": [c.to_dict() for c in self.constructors],
            "nested_types": [t.to_dict() for t in self.nested_types],
            "source": self.source.to_dict() if self.source else None,
        }


@dataclass
class EndpointInfo:
    http_method: str
    path: str
    handler_class: str
    handler_method: str
    annotations: list[AnnotationInfo] = field(default_factory=list)
    source: SourceRef | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "http_method": self.http_method,
            "path": self.path,
            "handler_class": self.handler_class,
            "handler_method": self.handler_method,
            "annotations": [a.to_dict() for a in self.annotations],
            "source": self.source.to_dict() if self.source else None,
        }


@dataclass
class DatabaseReference:
    """Table/column reference derived from JPA annotations (evidence-backed)."""

    kind: Literal["table", "column", "entity"]
    name: str
    owning_type: str
    source: SourceRef | None = None
    details: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "name": self.name,
            "owning_type": self.owning_type,
            "details": self.details,
            "source": self.source.to_dict() if self.source else None,
        }


@dataclass
class ParsedFile:
    file_path: str
    package: str | None = None
    imports: list[ImportInfo] = field(default_factory=list)
    types: list[TypeInfo] = field(default_factory=list)
    endpoints: list[EndpointInfo] = field(default_factory=list)
    database_references: list[DatabaseReference] = field(default_factory=list)
    spring_annotations: list[AnnotationInfo] = field(default_factory=list)
    parse_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "package": self.package,
            "imports": [i.to_dict() for i in self.imports],
            "types": [t.to_dict() for t in self.types],
            "endpoints": [e.to_dict() for e in self.endpoints],
            "database_references": [d.to_dict() for d in self.database_references],
            "spring_annotations": [a.to_dict() for a in self.spring_annotations],
            "parse_error": self.parse_error,
        }


@dataclass
class ParseResult:
    files: list[ParsedFile] = field(default_factory=list)
    packages: list[str] = field(default_factory=list)
    classes: list[TypeInfo] = field(default_factory=list)
    interfaces: list[TypeInfo] = field(default_factory=list)
    enums: list[TypeInfo] = field(default_factory=list)
    methods: list[MethodInfo] = field(default_factory=list)
    constructors: list[MethodInfo] = field(default_factory=list)
    fields: list[FieldInfo] = field(default_factory=list)
    imports: list[ImportInfo] = field(default_factory=list)
    endpoints: list[EndpointInfo] = field(default_factory=list)
    database_references: list[DatabaseReference] = field(default_factory=list)
    spring_annotations: list[AnnotationInfo] = field(default_factory=list)
    parse_errors: list[dict[str, str]] = field(default_factory=list)
    files_parsed: int = 0
    files_failed: int = 0

    def summary_lines(self) -> list[str]:
        return [
            f"✓ Java files parsed ({self.files_parsed}"
            + (f", {self.files_failed} failed" if self.files_failed else "")
            + ")",
            f"✓ Packages discovered ({len(self.packages)})",
            f"✓ Classes discovered ({len(self.classes)})",
            f"✓ Interfaces discovered ({len(self.interfaces)})",
            f"✓ Methods discovered ({len(self.methods)})",
            f"✓ Imports extracted ({len(self.imports)})",
            f"✓ REST endpoints discovered ({len(self.endpoints)})",
            f"✓ Database references discovered ({len(self.database_references)})",
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "files_parsed": self.files_parsed,
            "files_failed": self.files_failed,
            "packages": self.packages,
            "classes": [t.to_dict() for t in self.classes],
            "interfaces": [t.to_dict() for t in self.interfaces],
            "enums": [t.to_dict() for t in self.enums],
            "methods": [m.to_dict() for m in self.methods],
            "constructors": [c.to_dict() for c in self.constructors],
            "fields": [f.to_dict() for f in self.fields],
            "imports": [i.to_dict() for i in self.imports],
            "endpoints": [e.to_dict() for e in self.endpoints],
            "database_references": [d.to_dict() for d in self.database_references],
            "spring_annotations": [a.to_dict() for a in self.spring_annotations],
            "parse_errors": self.parse_errors,
            "files": [f.to_dict() for f in self.files],
        }
