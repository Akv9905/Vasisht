"""Java parser package (P2).

Provides a replaceable parser abstraction and a local javalang-backed implementation.
"""

from app.parser.base import JavaParser, aggregate_parse_results
from app.parser.javalang_parser import JavalangJavaParser
from app.parser.models import (
    AnnotationInfo,
    DatabaseReference,
    EndpointInfo,
    FieldInfo,
    ImportInfo,
    MethodCallInfo,
    MethodInfo,
    ParameterInfo,
    ParsedFile,
    ParseResult,
    SourceRef,
    TypeInfo,
)
from app.parser.service import get_default_parser, parse_java_files, parse_repository_java

__all__ = [
    "AnnotationInfo",
    "DatabaseReference",
    "EndpointInfo",
    "FieldInfo",
    "ImportInfo",
    "JavaParser",
    "JavalangJavaParser",
    "MethodCallInfo",
    "MethodInfo",
    "ParameterInfo",
    "ParsedFile",
    "ParseResult",
    "SourceRef",
    "TypeInfo",
    "aggregate_parse_results",
    "get_default_parser",
    "parse_java_files",
    "parse_repository_java",
]
