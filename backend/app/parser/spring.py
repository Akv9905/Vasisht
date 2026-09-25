"""Spring / JPA annotation helpers for deterministic extraction."""

from __future__ import annotations

from app.parser.models import AnnotationInfo

SPRING_ANNOTATIONS = frozenset(
    {
        "Controller",
        "RestController",
        "Service",
        "Repository",
        "Component",
        "Autowired",
        "GetMapping",
        "PostMapping",
        "PutMapping",
        "DeleteMapping",
        "PatchMapping",
        "RequestMapping",
        "Entity",
        "Table",
        "Column",
        "Id",
        "GeneratedValue",
        "Transactional",
        "SpringBootApplication",
        "RequestBody",
        "PathVariable",
        "RequestParam",
    }
)

MAPPING_ANNOTATIONS = frozenset(
    {
        "GetMapping",
        "PostMapping",
        "PutMapping",
        "DeleteMapping",
        "PatchMapping",
        "RequestMapping",
    }
)

HTTP_METHOD_BY_ANNOTATION = {
    "GetMapping": "GET",
    "PostMapping": "POST",
    "PutMapping": "PUT",
    "DeleteMapping": "DELETE",
    "PatchMapping": "PATCH",
}


def simple_annotation_name(name: str) -> str:
    """Strip package prefix from an annotation name."""
    return name.rsplit(".", 1)[-1]


def is_spring_annotation(name: str) -> bool:
    return simple_annotation_name(name) in SPRING_ANNOTATIONS


def is_mapping_annotation(name: str) -> bool:
    return simple_annotation_name(name) in MAPPING_ANNOTATIONS


def annotation_http_method(ann: AnnotationInfo) -> str | None:
    simple = simple_annotation_name(ann.name)
    if simple in HTTP_METHOD_BY_ANNOTATION:
        return HTTP_METHOD_BY_ANNOTATION[simple]
    if simple == "RequestMapping":
        method = ann.arguments.get("method") or ann.arguments.get("RequestMethod")
        if method:
            # e.g. RequestMethod.GET or GET
            return method.rsplit(".", 1)[-1].upper()
        return "REQUEST"
    return None


def annotation_path(ann: AnnotationInfo) -> str:
    """Extract path from mapping annotation arguments."""
    for key in ("value", "path", ""):
        if key in ann.arguments and ann.arguments[key]:
            raw = ann.arguments[key].strip()
            # Drop surrounding quotes / braces from array form {"/x"}
            raw = raw.strip("{}").strip()
            if "," in raw:
                raw = raw.split(",", 1)[0].strip()
            return raw.strip('"').strip("'")
    return ""


def join_paths(*parts: str) -> str:
    cleaned: list[str] = []
    for part in parts:
        if not part:
            continue
        piece = part.strip()
        if not piece:
            continue
        cleaned.append(piece.strip("/"))
    if not cleaned:
        return "/"
    return "/" + "/".join(p for p in cleaned if p)
