"""SQLAlchemy persistence models for repository analysis and follow-on features."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


JSON_VALUE = JSON().with_variant(JSONB, "postgresql")


class Base(DeclarativeBase):
    """Base metadata shared by application models and Alembic migrations."""


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Project(Base, TimestampMixin):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)


class Repository(Base, TimestampMixin):
    __tablename__ = "repositories"
    __table_args__ = (
        UniqueConstraint("project_id", "source", name="uq_repositories_project_source"),
        Index("ix_repositories_project_id", "project_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    root_path: Mapped[str] = mapped_column(Text, nullable=False)
    from_zip: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"
    __table_args__ = (Index("ix_analysis_runs_repository_started", "repository_id", "started_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="completed")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    file_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    java_file_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    parsed_file_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_file_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    graph_node_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    graph_edge_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    summary_json: Mapped[dict] = mapped_column(JSON_VALUE, default=dict, nullable=False)
    errors_json: Mapped[list] = mapped_column(JSON_VALUE, default=list, nullable=False)


class FileRecord(Base):
    __tablename__ = "files"
    __table_args__ = (
        UniqueConstraint("analysis_run_id", "relative_path", name="uq_files_run_relative_path"),
        Index("ix_files_repository_path", "repository_id", "relative_path"),
        Index("ix_files_analysis_run_id", "analysis_run_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False)
    analysis_run_id: Mapped[int] = mapped_column(ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False)
    relative_path: Mapped[str] = mapped_column(Text, nullable=False)
    absolute_path: Mapped[str | None] = mapped_column(Text)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    categories_json: Mapped[list] = mapped_column(JSON_VALUE, default=list, nullable=False)


class Package(Base):
    __tablename__ = "packages"
    __table_args__ = (UniqueConstraint("analysis_run_id", "name", name="uq_packages_run_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    analysis_run_id: Mapped[int] = mapped_column(ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)


class ClassSymbol(Base):
    __tablename__ = "classes"
    __table_args__ = (
        UniqueConstraint("analysis_run_id", "qualified_name", "kind", name="uq_classes_run_qname_kind"),
        Index("ix_classes_run_name", "analysis_run_id", "name"),
        Index("ix_classes_file_id", "file_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    analysis_run_id: Mapped[int] = mapped_column(ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False)
    file_id: Mapped[int | None] = mapped_column(ForeignKey("files.id", ondelete="SET NULL"))
    package_id: Mapped[int | None] = mapped_column(ForeignKey("packages.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    qualified_name: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    modifiers_json: Mapped[list] = mapped_column(JSON_VALUE, default=list, nullable=False)
    annotations_json: Mapped[list] = mapped_column(JSON_VALUE, default=list, nullable=False)
    extends_json: Mapped[list] = mapped_column(JSON_VALUE, default=list, nullable=False)
    implements_json: Mapped[list] = mapped_column(JSON_VALUE, default=list, nullable=False)
    start_line: Mapped[int | None] = mapped_column(Integer)
    end_line: Mapped[int | None] = mapped_column(Integer)


class Method(Base):
    __tablename__ = "methods"
    __table_args__ = (
        Index("ix_methods_run_name", "analysis_run_id", "name"),
        Index("ix_methods_class_id", "class_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    analysis_run_id: Mapped[int] = mapped_column(ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False)
    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    signature: Mapped[str] = mapped_column(Text, nullable=False)
    return_type: Mapped[str | None] = mapped_column(Text)
    parameters_json: Mapped[list] = mapped_column(JSON_VALUE, default=list, nullable=False)
    modifiers_json: Mapped[list] = mapped_column(JSON_VALUE, default=list, nullable=False)
    annotations_json: Mapped[list] = mapped_column(JSON_VALUE, default=list, nullable=False)
    throws_json: Mapped[list] = mapped_column(JSON_VALUE, default=list, nullable=False)
    calls_json: Mapped[list] = mapped_column(JSON_VALUE, default=list, nullable=False)
    is_constructor: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    start_line: Mapped[int | None] = mapped_column(Integer)
    end_line: Mapped[int | None] = mapped_column(Integer)


class Field(Base):
    __tablename__ = "fields"
    __table_args__ = (Index("ix_fields_class_id", "class_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    analysis_run_id: Mapped[int] = mapped_column(ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False)
    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    type_name: Mapped[str] = mapped_column(Text, nullable=False)
    modifiers_json: Mapped[list] = mapped_column(JSON_VALUE, default=list, nullable=False)
    annotations_json: Mapped[list] = mapped_column(JSON_VALUE, default=list, nullable=False)
    start_line: Mapped[int | None] = mapped_column(Integer)
    end_line: Mapped[int | None] = mapped_column(Integer)


class ImportRecord(Base):
    __tablename__ = "imports"
    __table_args__ = (Index("ix_imports_run_path", "analysis_run_id", "path"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    analysis_run_id: Mapped[int] = mapped_column(ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False)
    file_id: Mapped[int] = mapped_column(ForeignKey("files.id", ondelete="CASCADE"), nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    is_static: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_wildcard: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    start_line: Mapped[int | None] = mapped_column(Integer)


class GraphNode(Base):
    __tablename__ = "graph_nodes"
    __table_args__ = (
        UniqueConstraint("analysis_run_id", "graph_id", name="uq_graph_nodes_run_graph_id"),
        Index("ix_graph_nodes_run_kind", "analysis_run_id", "kind"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    analysis_run_id: Mapped[int] = mapped_column(ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False)
    graph_id: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    qualified_name: Mapped[str | None] = mapped_column(Text)
    file_path: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON_VALUE, default=dict, nullable=False)


class GraphEdge(Base):
    __tablename__ = "graph_edges"
    __table_args__ = (
        ForeignKeyConstraint(
            ["analysis_run_id", "source_graph_id"],
            ["graph_nodes.analysis_run_id", "graph_nodes.graph_id"],
            ondelete="CASCADE",
            name="fk_graph_edges_source_node",
        ),
        ForeignKeyConstraint(
            ["analysis_run_id", "target_graph_id"],
            ["graph_nodes.analysis_run_id", "graph_nodes.graph_id"],
            ondelete="CASCADE",
            name="fk_graph_edges_target_node",
        ),
        Index("ix_graph_edges_run_source", "analysis_run_id", "source_graph_id"),
        Index("ix_graph_edges_run_target", "analysis_run_id", "target_graph_id"),
        Index("ix_graph_edges_run_relationship", "analysis_run_id", "relationship"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    analysis_run_id: Mapped[int] = mapped_column(ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False)
    source_graph_id: Mapped[str] = mapped_column(Text, nullable=False)
    target_graph_id: Mapped[str] = mapped_column(Text, nullable=False)
    relationship: Mapped[str] = mapped_column(String(40), nullable=False)
    resolved: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON_VALUE, default=dict, nullable=False)


class Dependency(Base):
    __tablename__ = "dependencies"
    __table_args__ = (Index("ix_dependencies_run_source", "analysis_run_id", "source_graph_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    analysis_run_id: Mapped[int] = mapped_column(ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False)
    source_graph_id: Mapped[str] = mapped_column(Text, nullable=False)
    target_graph_id: Mapped[str] = mapped_column(Text, nullable=False)
    relationship: Mapped[str] = mapped_column(String(40), nullable=False)
    resolved: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    details_json: Mapped[dict] = mapped_column(JSON_VALUE, default=dict, nullable=False)


class ApiEndpoint(Base):
    __tablename__ = "api_endpoints"
    __table_args__ = (Index("ix_api_endpoints_run_path", "analysis_run_id", "path"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    analysis_run_id: Mapped[int] = mapped_column(ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False)
    file_id: Mapped[int | None] = mapped_column(ForeignKey("files.id", ondelete="SET NULL"))
    class_id: Mapped[int | None] = mapped_column(ForeignKey("classes.id", ondelete="SET NULL"))
    http_method: Mapped[str] = mapped_column(String(20), nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    handler_class: Mapped[str] = mapped_column(Text, nullable=False)
    handler_method: Mapped[str] = mapped_column(String(500), nullable=False)
    annotations_json: Mapped[list] = mapped_column(JSON_VALUE, default=list, nullable=False)
    start_line: Mapped[int | None] = mapped_column(Integer)
    end_line: Mapped[int | None] = mapped_column(Integer)


class DatabaseReference(Base):
    __tablename__ = "database_references"
    __table_args__ = (Index("ix_database_references_run_name", "analysis_run_id", "name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    analysis_run_id: Mapped[int] = mapped_column(ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False)
    file_id: Mapped[int | None] = mapped_column(ForeignKey("files.id", ondelete="SET NULL"))
    class_id: Mapped[int | None] = mapped_column(ForeignKey("classes.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    owning_type: Mapped[str] = mapped_column(Text, nullable=False)
    details_json: Mapped[dict] = mapped_column(JSON_VALUE, default=dict, nullable=False)
    start_line: Mapped[int | None] = mapped_column(Integer)
    end_line: Mapped[int | None] = mapped_column(Integer)


# Tables reserved by the Phase 1 schema for capabilities implemented in later phases.
class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False)
    analysis_run_id: Mapped[int | None] = mapped_column(ForeignKey("analysis_runs.id", ondelete="CASCADE"))
    file_id: Mapped[int | None] = mapped_column(ForeignKey("files.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(Text, nullable=False)
    uri: Mapped[str | None] = mapped_column(Text)
    mime_type: Mapped[str | None] = mapped_column(String(200))
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON_VALUE, default=dict, nullable=False)


class CodeChunk(Base):
    __tablename__ = "code_chunks"
    __table_args__ = (Index("ix_code_chunks_run_file", "analysis_run_id", "file_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    analysis_run_id: Mapped[int] = mapped_column(ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False)
    file_id: Mapped[int | None] = mapped_column(ForeignKey("files.id", ondelete="SET NULL"))
    symbol_ref: Mapped[str | None] = mapped_column(Text)
    symbol_type: Mapped[str | None] = mapped_column(String(80))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    start_line: Mapped[int | None] = mapped_column(Integer)
    end_line: Mapped[int | None] = mapped_column(Integer)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON_VALUE, default=dict, nullable=False)
    embedding_json: Mapped[list | None] = mapped_column(JSON_VALUE)


class Question(Base, TimestampMixin):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    analysis_run_id: Mapped[int | None] = mapped_column(ForeignKey("analysis_runs.id", ondelete="SET NULL"))
    question: Mapped[str] = mapped_column(Text, nullable=False)


class Answer(Base, TimestampMixin):
    __tablename__ = "answers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(String(100), default="deterministic", nullable=False)
    limitations_json: Mapped[list] = mapped_column(JSON_VALUE, default=list, nullable=False)


class Evidence(Base):
    __tablename__ = "evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    answer_id: Mapped[int] = mapped_column(ForeignKey("answers.id", ondelete="CASCADE"), nullable=False)
    file_id: Mapped[int | None] = mapped_column(ForeignKey("files.id", ondelete="SET NULL"))
    symbol_ref: Mapped[str | None] = mapped_column(Text)
    excerpt: Mapped[str | None] = mapped_column(Text)
    start_line: Mapped[int | None] = mapped_column(Integer)
    end_line: Mapped[int | None] = mapped_column(Integer)
    details_json: Mapped[dict] = mapped_column(JSON_VALUE, default=dict, nullable=False)


class ImpactAnalysis(Base):
    __tablename__ = "impact_analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    analysis_run_id: Mapped[int] = mapped_column(ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False)
    target_symbol: Mapped[str] = mapped_column(Text, nullable=False)
    traversal_depth: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    result_json: Mapped[dict] = mapped_column(JSON_VALUE, default=dict, nullable=False)


class RiskFinding(Base):
    __tablename__ = "risk_findings"
    __table_args__ = (Index("ix_risk_findings_run_severity", "analysis_run_id", "severity"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    analysis_run_id: Mapped[int] = mapped_column(ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False)
    finding_type: Mapped[str] = mapped_column(String(100), nullable=False)
    severity: Mapped[str] = mapped_column(String(40), nullable=False)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_json: Mapped[list] = mapped_column(JSON_VALUE, default=list, nullable=False)


class ModernizationFinding(Base):
    __tablename__ = "modernization_findings"
    __table_args__ = (Index("ix_modernization_findings_run_type", "analysis_run_id", "finding_type"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    analysis_run_id: Mapped[int] = mapped_column(ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False)
    finding_type: Mapped[str] = mapped_column(String(100), nullable=False)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    possible_direction: Mapped[str | None] = mapped_column(Text)
    risk: Mapped[str | None] = mapped_column(Text)
    investigation_order: Mapped[int | None] = mapped_column(Integer)
    evidence_json: Mapped[list] = mapped_column(JSON_VALUE, default=list, nullable=False)


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    display_name: Mapped[str | None] = mapped_column(String(200))
    password_hash: Mapped[str | None] = mapped_column(Text)
    roles_json: Mapped[list] = mapped_column(JSON_VALUE, default=list, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_logs_project_created", "project_id", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(100))
    entity_id: Mapped[str | None] = mapped_column(Text)
    details_json: Mapped[dict] = mapped_column(JSON_VALUE, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


__all__ = [
    "Answer", "AnalysisRun", "ApiEndpoint", "AuditLog", "Base", "ClassSymbol",
    "CodeChunk", "DatabaseReference", "Dependency", "Document", "Evidence", "Field",
    "FileRecord", "GraphEdge", "GraphNode", "ImpactAnalysis", "ImportRecord", "Method",
    "ModernizationFinding", "Package", "Project", "Question", "Repository", "RiskFinding", "User",
]
