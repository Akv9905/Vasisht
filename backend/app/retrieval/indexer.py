"""Codebase content indexer for semantic and keyword retrieval (P8).

Indexes:
- Java classes (class signature, annotations, hierarchy, docstrings)
- Methods (signature, return type, parameters, annotations, calls)
- Documentation (markdown, docs)
- Configuration (application.properties, YAML, pom.xml)
- SQL (schema.sql, queries, migrations)
- README files (README.md, README)

Stores metadata:
- project_id
- repository_id
- file_id
- class_id
- method_id
- symbol_type
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import (
    AnalysisRun,
    ClassSymbol,
    CodeChunk,
    Document,
    FileRecord,
    Method,
    Project,
    Repository,
)
from app.retrieval.embeddings import EmbeddingProvider, get_embedding_provider

logger = logging.getLogger(__name__)


@dataclass
class IndexingSummary:
    analysis_run_id: int
    classes_indexed: int = 0
    methods_indexed: int = 0
    documents_indexed: int = 0
    configuration_indexed: int = 0
    sql_indexed: int = 0
    readme_indexed: int = 0
    total_chunks: int = 0
    embeddings_generated: bool = False
    provider_name: str = "none"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _read_file_safe(path: str | None, max_bytes: int = 500_000) -> str | None:
    if not path:
        return None
    p = Path(path)
    if not p.is_file():
        return None
    try:
        return p.read_text(encoding="utf-8", errors="replace")[:max_bytes]
    except Exception:
        return None


def _chunk_text(text: str, chunk_size: int = 1200, overlap: int = 150) -> list[tuple[str, int, int]]:
    """Split text into overlapping chunks, tracking approximate line ranges."""
    lines = text.splitlines(keepends=True)
    chunks: list[tuple[str, int, int]] = []
    current_lines: list[str] = []
    current_len = 0
    start_line = 1

    for idx, line in enumerate(lines, start=1):
        current_lines.append(line)
        current_len += len(line)
        if current_len >= chunk_size:
            chunk_content = "".join(current_lines).strip()
            if chunk_content:
                chunks.append((chunk_content, start_line, idx))
            # Keep overlap lines
            kept: list[str] = []
            kept_len = 0
            for l in reversed(current_lines):
                if kept_len + len(l) > overlap:
                    break
                kept.insert(0, l)
                kept_len += len(l)
            current_lines = kept
            current_len = kept_len
            start_line = max(1, idx - len(kept) + 1)

    if current_lines:
        chunk_content = "".join(current_lines).strip()
        if chunk_content:
            chunks.append((chunk_content, start_line, len(lines)))

    return chunks if chunks else [("", 1, 1)]


def index_analysis_run(
    session: Session,
    analysis_run_id: int,
    embedding_provider: EmbeddingProvider | None = None,
    chunk_size: int = 1200,
) -> IndexingSummary:
    """Index an analysis run for semantic and keyword retrieval."""
    run = session.get(AnalysisRun, analysis_run_id)
    if not run:
        raise ValueError(f"AnalysisRun id={analysis_run_id} not found.")

    repo = session.get(Repository, run.repository_id)
    project_id = repo.project_id if repo else None
    repository_id = repo.id if repo else None

    provider = embedding_provider or get_embedding_provider()
    provider_available = provider.is_available()
    provider_name = provider.__class__.__name__

    # Clean existing chunks and documents for this run
    session.execute(delete(CodeChunk).where(CodeChunk.analysis_run_id == analysis_run_id))
    session.execute(delete(Document).where(Document.analysis_run_id == analysis_run_id))
    session.flush()

    chunks_to_create: list[CodeChunk] = []
    summary = IndexingSummary(
        analysis_run_id=analysis_run_id,
        embeddings_generated=provider_available,
        provider_name=provider_name,
    )

    # 1. Index Java Classes
    classes = session.scalars(
        select(ClassSymbol).where(ClassSymbol.analysis_run_id == analysis_run_id)
    ).all()

    for cls in classes:
        annotations = [
            f"@{a.get('name', '')}"
            for a in (cls.annotations_json or [])
            if isinstance(a, dict)
        ]
        ann_str = ", ".join(annotations)
        extends_str = ", ".join(cls.extends_json or [])
        implements_str = ", ".join(cls.implements_json or [])

        content = (
            f"Class: {cls.qualified_name}\n"
            f"Simple Name: {cls.name}\n"
            f"Kind: {cls.kind}\n"
            f"Annotations: {ann_str or 'None'}\n"
            f"Extends: {extends_str or 'None'}\n"
            f"Implements: {implements_str or 'None'}"
        )

        meta = {
            "project_id": project_id,
            "repository_id": repository_id,
            "file_id": cls.file_id,
            "class_id": cls.id,
            "method_id": None,
            "symbol_type": "class",
            "name": cls.name,
            "qualified_name": cls.qualified_name,
        }

        chunks_to_create.append(
            CodeChunk(
                analysis_run_id=analysis_run_id,
                file_id=cls.file_id,
                symbol_ref=cls.qualified_name,
                symbol_type="class",
                content=content,
                start_line=cls.start_line,
                end_line=cls.end_line,
                metadata_json=meta,
            )
        )
        summary.classes_indexed += 1

    # 2. Index Java Methods
    methods_with_class = session.execute(
        select(Method, ClassSymbol)
        .join(ClassSymbol, Method.class_id == ClassSymbol.id)
        .where(Method.analysis_run_id == analysis_run_id)
    ).all()

    for method, cls in methods_with_class:
        annotations = [
            f"@{a.get('name', '')}"
            for a in (method.annotations_json or [])
            if isinstance(a, dict)
        ]
        ann_str = ", ".join(annotations)
        calls = [
            c.get("callee_method", "")
            for c in (method.calls_json or [])
            if isinstance(c, dict)
        ]
        calls_str = ", ".join(filter(None, calls))

        content = (
            f"Method: {cls.name}.{method.name}\n"
            f"Class: {cls.qualified_name}\n"
            f"Signature: {method.signature}\n"
            f"Return Type: {method.return_type or 'void'}\n"
            f"Annotations: {ann_str or 'None'}\n"
            f"Calls: {calls_str or 'None'}"
        )

        meta = {
            "project_id": project_id,
            "repository_id": repository_id,
            "file_id": cls.file_id,
            "class_id": cls.id,
            "method_id": method.id,
            "symbol_type": "method",
            "class_name": cls.name,
            "method_name": method.name,
            "signature": method.signature,
        }

        chunks_to_create.append(
            CodeChunk(
                analysis_run_id=analysis_run_id,
                file_id=cls.file_id,
                symbol_ref=f"{cls.qualified_name}#{method.name}",
                symbol_type="method",
                content=content,
                start_line=method.start_line,
                end_line=method.end_line,
                metadata_json=meta,
            )
        )
        summary.methods_indexed += 1

    # 3. Index Documentation, README, Configuration, and SQL files
    file_records = session.scalars(
        select(FileRecord).where(FileRecord.analysis_run_id == analysis_run_id)
    ).all()

    for f_rec in file_records:
        cats = f_rec.categories_json or []
        rel_path = f_rec.relative_path
        lower_path = rel_path.lower()
        abs_path = f_rec.absolute_path

        is_readme = "readme" in lower_path
        is_doc = is_readme or "documentation" in cats or lower_path.endswith((".md", ".txt", ".adoc"))
        is_cfg = "configuration" in cats or lower_path.endswith((".properties", ".yml", ".yaml", ".xml"))
        is_sql = "sql" in cats or lower_path.endswith(".sql")

        if not (is_doc or is_cfg or is_sql):
            continue

        raw_text = _read_file_safe(abs_path)
        if not raw_text or not raw_text.strip():
            continue

        symbol_type = "documentation"
        mime_type = "text/plain"

        if is_readme:
            symbol_type = "readme"
            mime_type = "text/markdown"
            summary.readme_indexed += 1
        elif is_doc:
            symbol_type = "documentation"
            mime_type = "text/markdown" if lower_path.endswith(".md") else "text/plain"
            summary.documents_indexed += 1
        elif is_cfg:
            symbol_type = "configuration"
            mime_type = "text/yaml" if lower_path.endswith((".yml", ".yaml")) else "text/plain"
            summary.configuration_indexed += 1
        elif is_sql:
            symbol_type = "sql"
            mime_type = "application/sql"
            summary.sql_indexed += 1

        # Record in documents table
        doc_row = Document(
            repository_id=repository_id or 1,
            analysis_run_id=analysis_run_id,
            file_id=f_rec.id,
            title=rel_path,
            uri=abs_path,
            mime_type=mime_type,
            metadata_json={
                "project_id": project_id,
                "repository_id": repository_id,
                "file_id": f_rec.id,
                "symbol_type": symbol_type,
                "relative_path": rel_path,
            },
        )
        session.add(doc_row)

        # Create code chunks
        text_chunks = _chunk_text(raw_text, chunk_size=chunk_size)
        for chunk_text, start_l, end_l in text_chunks:
            meta = {
                "project_id": project_id,
                "repository_id": repository_id,
                "file_id": f_rec.id,
                "class_id": None,
                "method_id": None,
                "symbol_type": symbol_type,
                "file_path": rel_path,
            }
            chunks_to_create.append(
                CodeChunk(
                    analysis_run_id=analysis_run_id,
                    file_id=f_rec.id,
                    symbol_ref=rel_path,
                    symbol_type=symbol_type,
                    content=chunk_text,
                    start_line=start_l,
                    end_line=end_l,
                    metadata_json=meta,
                )
            )

    # 4. Generate embeddings if available
    summary.total_chunks = len(chunks_to_create)
    if provider_available and chunks_to_create:
        texts = [c.content for c in chunks_to_create]
        # Batch in chunks of 50 to avoid memory spikes
        batch_size = 50
        all_embeddings: list[list[float]] = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            emb_batch = provider.generate_embeddings(batch)
            all_embeddings.extend(emb_batch)

        for c, emb in zip(chunks_to_create, all_embeddings):
            if emb:
                c.embedding_json = emb

    session.add_all(chunks_to_create)
    session.flush()
    return summary
