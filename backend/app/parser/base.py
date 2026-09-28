"""Parser provider abstraction — replaceable Java parser backends."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from app.parser.models import ParsedFile, ParseResult


class JavaParser(ABC):
    """Abstract Java source parser. Implementations must stay local/free-capable."""

    name: str = "abstract"

    @abstractmethod
    def parse_source(self, source: str, file_path: str) -> ParsedFile:
        """Parse a single Java compilation unit."""

    def parse_file(self, path: Path, *, relative_path: str | None = None) -> ParsedFile:
        file_path = relative_path or str(path).replace("\\", "/")
        try:
            source = path.read_text(encoding="utf-8")
        except OSError as exc:
            return ParsedFile(file_path=file_path, parse_error=str(exc))
        return self.parse_source(source, file_path)

    def parse_files(
        self,
        root: Path,
        relative_java_files: list[str],
    ) -> ParseResult:
        """Parse many Java files under a repository root and aggregate metadata."""
        parsed_files: list[ParsedFile] = []
        for rel in relative_java_files:
            parsed_files.append(self.parse_file(root / rel, relative_path=rel.replace("\\", "/")))
        return aggregate_parse_results(parsed_files)


def aggregate_parse_results(files: list[ParsedFile]) -> ParseResult:
    result = ParseResult(files=files)
    packages: set[str] = set()
    spring_seen: set[tuple[str, str | None]] = set()

    for pf in files:
        if pf.parse_error:
            result.files_failed += 1
            result.parse_errors.append({"file_path": pf.file_path, "error": pf.parse_error})
            continue

        result.files_parsed += 1
        if pf.package:
            packages.add(pf.package)
        result.imports.extend(pf.imports)
        result.endpoints.extend(pf.endpoints)
        result.database_references.extend(pf.database_references)

        for ann in pf.spring_annotations:
            key = (ann.name, pf.file_path)
            if key not in spring_seen:
                spring_seen.add(key)
                result.spring_annotations.append(ann)

        _collect_types(pf.types, result)

    result.packages = sorted(packages)
    return result


def _collect_types(types: list, result: ParseResult) -> None:
    from app.parser.models import TypeInfo

    for t in types:
        assert isinstance(t, TypeInfo)
        if t.kind == "interface":
            result.interfaces.append(t)
        elif t.kind == "enum":
            result.enums.append(t)
        else:
            result.classes.append(t)
        result.fields.extend(t.fields)
        result.methods.extend(t.methods)
        result.constructors.extend(t.constructors)
        if t.nested_types:
            _collect_types(t.nested_types, result)
