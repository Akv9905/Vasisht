"""Local Java parser backed by the open-source javalang library."""

from __future__ import annotations

from typing import Any

import javalang
from javalang import tree

from app.parser.base import JavaParser
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
    SourceRef,
    TypeInfo,
    TypeKind,
)
from app.parser.spring import (
    annotation_http_method,
    annotation_path,
    is_mapping_annotation,
    is_spring_annotation,
    join_paths,
    simple_annotation_name,
)


class JavalangJavaParser(JavaParser):
    """Deterministic AST parser using javalang (local, no paid APIs)."""

    name = "javalang"

    def parse_source(self, source: str, file_path: str) -> ParsedFile:
        try:
            compilation_unit = javalang.parse.parse(source)

            package = compilation_unit.package.name if compilation_unit.package else None
            imports = [_convert_import(imp, file_path) for imp in (compilation_unit.imports or [])]

            types: list[TypeInfo] = []
            for type_decl in compilation_unit.types or []:
                types.append(_convert_type(type_decl, package, file_path))

            endpoints: list[EndpointInfo] = []
            db_refs: list[DatabaseReference] = []
            spring_anns: list[AnnotationInfo] = []

            for t in types:
                endpoints.extend(_extract_endpoints(t))
                db_refs.extend(_extract_database_refs(t))
                spring_anns.extend(_collect_spring_annotations(t))

            return ParsedFile(
                file_path=file_path,
                package=package,
                imports=imports,
                types=types,
                endpoints=endpoints,
                database_references=db_refs,
                spring_annotations=spring_anns,
            )
        except javalang.parser.JavaSyntaxError as exc:
            return ParsedFile(file_path=file_path, parse_error=f"JavaSyntaxError: {exc}")
        except Exception as exc:  # noqa: BLE001 — keep per-file failures isolated
            return ParsedFile(file_path=file_path, parse_error=f"{type(exc).__name__}: {exc}")


def _line(node: Any) -> int | None:
    if node is None:
        return None
    position = getattr(node, "position", None)
    if position is None:
        return None
    return getattr(position, "line", None)


def _source(file_path: str, node: Any) -> SourceRef:
    return SourceRef(file_path=file_path, start_line=_line(node))


def _type_name(type_node: Any) -> str:
    if type_node is None:
        return "void"
    if isinstance(type_node, tree.BasicType):
        name = type_node.name
    elif isinstance(type_node, tree.ReferenceType):
        parts = [type_node.name]
        current = type_node
        while getattr(current, "sub_type", None) is not None:
            current = current.sub_type
            parts.append(current.name)
        name = ".".join(parts)
        if type_node.arguments:
            args = []
            for arg in type_node.arguments:
                if arg is None:
                    continue
                # TypeArgument has .type or wildcard
                inner = getattr(arg, "type", None)
                args.append(_type_name(inner) if inner is not None else "?")
            name = f"{name}<{', '.join(args)}>"
    elif isinstance(type_node, str):
        name = type_node
    else:
        name = getattr(type_node, "name", str(type_node))

    dims = getattr(type_node, "dimensions", None) or []
    if dims:
        name += "[]" * len(dims)
    return name


def _annotation_args(ann: tree.Annotation) -> dict[str, str]:
    args: dict[str, str] = {}
    element = ann.element
    if element is None:
        return args
    if isinstance(element, list):
        for item in element:
            if isinstance(item, tree.ElementValuePair):
                args[item.name] = _literal_to_str(item.value)
            else:
                args[""] = _literal_to_str(item)
    else:
        args[""] = _literal_to_str(element)
        # Also expose as value for convenience
        args.setdefault("value", args[""])
    return args


def _literal_to_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, tree.Literal):
        return str(value.value)
    if isinstance(value, tree.MemberReference):
        qualifier = ".".join(value.qualifier) if isinstance(value.qualifier, list) else (value.qualifier or "")
        if qualifier:
            return f"{qualifier}.{value.member}"
        return str(value.member)
    if isinstance(value, tree.ElementArrayValue):
        parts = [_literal_to_str(v) for v in (value.values or [])]
        return "{" + ", ".join(parts) + "}"
    if isinstance(value, tree.Annotation):
        return f"@{value.name}"
    if isinstance(value, tree.BinaryOperation):
        return f"{_literal_to_str(value.operandl)} {value.operator} {_literal_to_str(value.operandr)}"
    if isinstance(value, tree.MethodInvocation):
        return f"{value.member}(...)"
    return str(value)


def _convert_annotations(annotations: list[tree.Annotation] | None, file_path: str) -> list[AnnotationInfo]:
    result: list[AnnotationInfo] = []
    for ann in annotations or []:
        result.append(
            AnnotationInfo(
                name=ann.name,
                arguments=_annotation_args(ann),
                source=_source(file_path, ann),
            )
        )
    return result


def _convert_import(imp: tree.Import, file_path: str) -> ImportInfo:
    return ImportInfo(
        path=imp.path,
        is_static=bool(imp.static),
        is_wildcard=bool(imp.wildcard),
        source=_source(file_path, imp),
    )


def _kind_for(type_decl: tree.TypeDeclaration) -> TypeKind:
    if isinstance(type_decl, tree.ClassDeclaration):
        return "class"
    if isinstance(type_decl, tree.InterfaceDeclaration):
        return "interface"
    if isinstance(type_decl, tree.EnumDeclaration):
        return "enum"
    if isinstance(type_decl, tree.AnnotationDeclaration):
        return "annotation"
    return "unknown"


def _extends_list(type_decl: tree.TypeDeclaration) -> list[str]:
    extends = getattr(type_decl, "extends", None)
    if extends is None:
        return []
    if isinstance(extends, list):
        return [_type_name(t) for t in extends]
    return [_type_name(extends)]


def _implements_list(type_decl: tree.TypeDeclaration) -> list[str]:
    implements = getattr(type_decl, "implements", None) or []
    return [_type_name(t) for t in implements]


def _convert_field(field: tree.FieldDeclaration, file_path: str) -> list[FieldInfo]:
    type_name = _type_name(field.type)
    annotations = _convert_annotations(field.annotations, file_path)
    modifiers = _modifiers(field)
    results: list[FieldInfo] = []
    for declarator in field.declarators or []:
        results.append(
            FieldInfo(
                name=declarator.name,
                type_name=type_name,
                modifiers=modifiers,
                annotations=annotations,
                source=_source(file_path, field),
            )
        )
    return results


def _convert_parameter(param: tree.FormalParameter, file_path: str) -> ParameterInfo:
    return ParameterInfo(
        name=param.name,
        type_name=_type_name(param.type),
        annotations=_convert_annotations(param.annotations, file_path),
    )


def _walk_ast(node: Any):
    """Yield all javalang AST nodes under node (handles list bodies)."""
    if node is None:
        return
    if isinstance(node, list):
        for item in node:
            yield from _walk_ast(item)
        return
    if isinstance(node, tree.Node):
        yield node
        for attr in node.attrs:
            yield from _walk_ast(getattr(node, attr, None))


def _extract_method_calls(body: Any, file_path: str) -> list[MethodCallInfo]:
    calls: list[MethodCallInfo] = []
    for node in _walk_ast(body):
        if isinstance(node, tree.MethodInvocation):
            qualifier = None
            if node.qualifier:
                if isinstance(node.qualifier, list):
                    qualifier = ".".join(str(q) for q in node.qualifier)
                else:
                    qualifier = str(node.qualifier)
            calls.append(
                MethodCallInfo(
                    name=node.member,
                    qualifier=qualifier,
                    source=_source(file_path, node),
                )
            )
        elif isinstance(node, tree.SuperMethodInvocation):
            calls.append(
                MethodCallInfo(
                    name=node.member,
                    qualifier="super",
                    source=_source(file_path, node),
                )
            )
    return calls


def _build_signature(
    name: str,
    parameters: list[ParameterInfo],
    return_type: str | None,
    *,
    is_constructor: bool,
) -> str:
    params = ", ".join(f"{p.type_name} {p.name}" for p in parameters)
    if is_constructor:
        return f"{name}({params})"
    return f"{return_type or 'void'} {name}({params})"


def _convert_method(
    method: tree.MethodDeclaration,
    file_path: str,
) -> MethodInfo:
    parameters = [_convert_parameter(p, file_path) for p in (method.parameters or [])]
    return_type = _type_name(method.return_type) if method.return_type is not None else "void"
    annotations = _convert_annotations(method.annotations, file_path)
    throws = [_type_name(t) if not isinstance(t, str) else t for t in (method.throws or [])]
    calls = _extract_method_calls(method.body, file_path)
    return MethodInfo(
        name=method.name,
        return_type=return_type,
        parameters=parameters,
        modifiers=_modifiers(method),
        annotations=annotations,
        throws=throws,
        is_constructor=False,
        method_calls=calls,
        signature=_build_signature(method.name, parameters, return_type, is_constructor=False),
        source=_source(file_path, method),
    )


def _convert_constructor(
    ctor: tree.ConstructorDeclaration,
    file_path: str,
) -> MethodInfo:
    parameters = [_convert_parameter(p, file_path) for p in (ctor.parameters or [])]
    annotations = _convert_annotations(ctor.annotations, file_path)
    throws = [_type_name(t) if not isinstance(t, str) else t for t in (ctor.throws or [])]
    calls = _extract_method_calls(ctor.body, file_path)
    return MethodInfo(
        name=ctor.name,
        return_type=None,
        parameters=parameters,
        modifiers=_modifiers(ctor),
        annotations=annotations,
        throws=throws,
        is_constructor=True,
        method_calls=calls,
        signature=_build_signature(ctor.name, parameters, None, is_constructor=True),
        source=_source(file_path, ctor),
    )


def _modifiers(node: Any) -> list[str]:
    mods = getattr(node, "modifiers", None) or []
    if isinstance(mods, set):
        return sorted(mods)
    return list(mods)


def _convert_type(
    type_decl: tree.TypeDeclaration,
    package: str | None,
    file_path: str,
) -> TypeInfo:
    name = type_decl.name
    qualified = f"{package}.{name}" if package else name
    annotations = _convert_annotations(getattr(type_decl, "annotations", None), file_path)

    fields: list[FieldInfo] = []
    methods: list[MethodInfo] = []
    constructors: list[MethodInfo] = []
    nested: list[TypeInfo] = []

    body = getattr(type_decl, "body", None)
    body_items: list[Any]
    if isinstance(body, tree.EnumBody):
        body_items = [body]
    elif isinstance(body, list):
        body_items = body
    elif body is None:
        body_items = []
    else:
        body_items = [body]

    for body_item in body_items:
        if isinstance(body_item, tree.FieldDeclaration):
            fields.extend(_convert_field(body_item, file_path))
        elif isinstance(body_item, tree.MethodDeclaration):
            methods.append(_convert_method(body_item, file_path))
        elif isinstance(body_item, tree.ConstructorDeclaration):
            constructors.append(_convert_constructor(body_item, file_path))
        elif isinstance(body_item, tree.TypeDeclaration):
            nested.append(_convert_type(body_item, qualified, file_path))
        elif isinstance(body_item, tree.EnumBody):
            for const in body_item.constants or []:
                fields.append(
                    FieldInfo(
                        name=const.name,
                        type_name=name,
                        modifiers=["final", "public", "static"],
                        annotations=_convert_annotations(const.annotations, file_path),
                        source=_source(file_path, const),
                    )
                )
            for decl in body_item.declarations or []:
                if isinstance(decl, tree.FieldDeclaration):
                    fields.extend(_convert_field(decl, file_path))
                elif isinstance(decl, tree.MethodDeclaration):
                    methods.append(_convert_method(decl, file_path))
                elif isinstance(decl, tree.ConstructorDeclaration):
                    constructors.append(_convert_constructor(decl, file_path))
                elif isinstance(decl, tree.TypeDeclaration):
                    nested.append(_convert_type(decl, qualified, file_path))

    return TypeInfo(
        name=name,
        kind=_kind_for(type_decl),
        package=package,
        qualified_name=qualified,
        modifiers=_modifiers(type_decl),
        annotations=annotations,
        extends=_extends_list(type_decl),
        implements=_implements_list(type_decl),
        fields=fields,
        methods=methods,
        constructors=constructors,
        nested_types=nested,
        source=_source(file_path, type_decl),
    )


def _collect_spring_annotations(type_info: TypeInfo) -> list[AnnotationInfo]:
    found: list[AnnotationInfo] = []

    def consider(anns: list[AnnotationInfo]) -> None:
        for ann in anns:
            if is_spring_annotation(ann.name):
                found.append(ann)

    consider(type_info.annotations)
    for field in type_info.fields:
        consider(field.annotations)
    for method in type_info.methods + type_info.constructors:
        consider(method.annotations)
        for param in method.parameters:
            consider(param.annotations)
    for nested in type_info.nested_types:
        found.extend(_collect_spring_annotations(nested))
    return found


def _class_mapping_path(type_info: TypeInfo) -> str:
    for ann in type_info.annotations:
        if is_mapping_annotation(ann.name):
            return annotation_path(ann)
    return ""


def _extract_endpoints(type_info: TypeInfo) -> list[EndpointInfo]:
    class_path = _class_mapping_path(type_info)
    is_controller = any(
        simple_annotation_name(a.name) in {"RestController", "Controller"}
        for a in type_info.annotations
    )
    # Also treat types that only have RequestMapping as potential controllers
    if not is_controller and not class_path:
        # Still allow method-level mappings on @Component etc. if present
        pass

    endpoints: list[EndpointInfo] = []
    for method in type_info.methods:
        for ann in method.annotations:
            if not is_mapping_annotation(ann.name):
                continue
            http = annotation_http_method(ann) or "REQUEST"
            method_path = annotation_path(ann)
            full_path = join_paths(class_path, method_path)
            endpoints.append(
                EndpointInfo(
                    http_method=http,
                    path=full_path,
                    handler_class=type_info.qualified_name,
                    handler_method=method.name,
                    annotations=[ann],
                    source=method.source,
                )
            )
    for nested in type_info.nested_types:
        endpoints.extend(_extract_endpoints(nested))
    return endpoints


def _extract_database_refs(type_info: TypeInfo) -> list[DatabaseReference]:
    refs: list[DatabaseReference] = []
    has_entity = any(simple_annotation_name(a.name) == "Entity" for a in type_info.annotations)

    for ann in type_info.annotations:
        simple = simple_annotation_name(ann.name)
        if simple == "Entity":
            refs.append(
                DatabaseReference(
                    kind="entity",
                    name=type_info.name,
                    owning_type=type_info.qualified_name,
                    source=ann.source or type_info.source,
                )
            )
        elif simple == "Table":
            table_name = (
                ann.arguments.get("name")
                or ann.arguments.get("value")
                or ann.arguments.get("")
                or type_info.name
            )
            table_name = table_name.strip('"').strip("'")
            refs.append(
                DatabaseReference(
                    kind="table",
                    name=table_name,
                    owning_type=type_info.qualified_name,
                    source=ann.source or type_info.source,
                    details={"annotation": "Table"},
                )
            )

    if has_entity:
        for field in type_info.fields:
            for ann in field.annotations:
                if simple_annotation_name(ann.name) != "Column":
                    continue
                col_name = (
                    ann.arguments.get("name")
                    or ann.arguments.get("value")
                    or ann.arguments.get("")
                    or field.name
                )
                col_name = col_name.strip('"').strip("'")
                refs.append(
                    DatabaseReference(
                        kind="column",
                        name=col_name,
                        owning_type=type_info.qualified_name,
                        source=ann.source or field.source,
                        details={"field": field.name},
                    )
                )

    for nested in type_info.nested_types:
        refs.extend(_extract_database_refs(nested))
    return refs
