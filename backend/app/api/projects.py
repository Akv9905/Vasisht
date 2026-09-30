"""Project, repository, and codebase inventory endpoints (P17).

Endpoints:
- POST /projects
- GET  /projects
- GET  /projects/{id}
- POST /projects/{id}/repositories
- POST /projects/{id}/analyze
- GET  /projects/{id}/files
- GET  /projects/{id}/classes
- GET  /projects/{id}/methods
- GET  /projects/{id}/analysis-runs
"""

from __future__ import annotations

from datetime import datetime
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.graph.extractor import extract_dependencies
from app.ingestion.scanner import scan_path
from app.models import (
    AnalysisRun,
    ClassSymbol,
    FileRecord,
    Method,
    Project,
    Repository,
)
from app.parser import parse_java_files
from app.persistence import persist_analysis

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects", tags=["projects"])


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------


class ProjectCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200, description="Unique project name")
    description: str | None = Field(None, description="Optional project description")


class ProjectResponse(BaseModel):
    id: int
    name: str
    description: str | None = None
    created_at: datetime | None = None


class RepositoryCreateRequest(BaseModel):
    source: str = Field(..., min_length=1, description="Local directory path or ZIP file path")


class RepositoryResponse(BaseModel):
    id: int
    project_id: int
    source: str
    root_path: str
    from_zip: bool
    created_at: datetime | None = None


class AnalyzeRequest(BaseModel):
    source_path: str | None = Field(None, description="Optional override path for analysis")


class AnalyzeResponse(BaseModel):
    analysis_run_id: int
    project_id: int
    repository_id: int
    status: str
    file_count: int
    java_file_count: int
    graph_node_count: int
    graph_edge_count: int


class FileItemResponse(BaseModel):
    id: int
    relative_path: str
    size_bytes: int
    categories: list[str]


class ClassItemResponse(BaseModel):
    id: int
    name: str
    qualified_name: str
    kind: str
    start_line: int | None = None
    end_line: int | None = None
    modifiers: list[str] = []
    annotations: list[dict[str, Any]] = []


class MethodItemResponse(BaseModel):
    id: int
    class_id: int
    name: str
    signature: str
    return_type: str | None = None
    is_constructor: bool = False
    start_line: int | None = None
    end_line: int | None = None


class AnalysisRunItemResponse(BaseModel):
    id: int
    repository_id: int
    status: str
    started_at: datetime
    completed_at: datetime | None = None
    file_count: int
    java_file_count: int
    graph_node_count: int
    graph_edge_count: int


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _get_project_or_404(session: Session, project_id: int) -> Project:
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID {project_id} not found.",
        )
    return project


def _get_latest_run_or_404(session: Session, project_id: int) -> AnalysisRun:
    run = session.scalar(
        select(AnalysisRun)
        .join(Repository, AnalysisRun.repository_id == Repository.id)
        .where(
            Repository.project_id == project_id,
            AnalysisRun.status.in_(["completed", "completed_with_errors"]),
        )
        .order_by(AnalysisRun.id.desc())
        .limit(1)
    )
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No completed analysis runs found for project {project_id}.",
        )
    return run


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new project",
)
def create_project(
    body: ProjectCreateRequest,
    db: Session = Depends(get_db),
) -> ProjectResponse:
    existing = db.scalar(select(Project).where(Project.name == body.name.strip()))
    if existing:
        return ProjectResponse(
            id=existing.id,
            name=existing.name,
            description=existing.description,
            created_at=existing.created_at,
        )

    project = Project(name=body.name.strip(), description=body.description)
    db.add(project)
    db.commit()
    db.refresh(project)

    return ProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        created_at=project.created_at,
    )


@router.get(
    "",
    response_model=list[ProjectResponse],
    summary="List all projects",
)
def list_projects(
    db: Session = Depends(get_db),
) -> list[ProjectResponse]:
    projects = db.scalars(select(Project).order_by(Project.id.asc())).all()
    return [
        ProjectResponse(
            id=p.id,
            name=p.name,
            description=p.description,
            created_at=p.created_at,
        )
        for p in projects
    ]


@router.get(
    "/{project_id}",
    response_model=ProjectResponse,
    summary="Get project details by ID",
)
def get_project(
    project_id: int,
    db: Session = Depends(get_db),
) -> ProjectResponse:
    project = _get_project_or_404(db, project_id)
    return ProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        created_at=project.created_at,
    )


@router.post(
    "/{project_id}/repositories",
    response_model=RepositoryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Attach a repository to a project",
)
def add_repository(
    project_id: int,
    body: RepositoryCreateRequest,
    db: Session = Depends(get_db),
) -> RepositoryResponse:
    _get_project_or_404(db, project_id)

    src_path = Path(body.source).resolve()
    if not src_path.exists():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Source path '{body.source}' does not exist on disk.",
        )

    from_zip = src_path.is_file() and src_path.suffix.lower() == ".zip"
    source_str = str(src_path)

    existing = db.scalar(
        select(Repository).where(
            Repository.project_id == project_id,
            Repository.source == source_str,
        )
    )
    if existing:
        return RepositoryResponse(
            id=existing.id,
            project_id=existing.project_id,
            source=existing.source,
            root_path=existing.root_path,
            from_zip=existing.from_zip,
            created_at=existing.created_at,
        )

    repo = Repository(
        project_id=project_id,
        source=source_str,
        root_path=source_str,
        from_zip=from_zip,
    )
    db.add(repo)
    db.commit()
    db.refresh(repo)

    return RepositoryResponse(
        id=repo.id,
        project_id=repo.project_id,
        source=repo.source,
        root_path=repo.root_path,
        from_zip=repo.from_zip,
        created_at=repo.created_at,
    )


@router.post(
    "/{project_id}/analyze",
    response_model=AnalyzeResponse,
    status_code=status.HTTP_200_OK,
    summary="Run full analysis (scan, parse, graph, persist) for a project",
)
def run_project_analysis(
    project_id: int,
    body: AnalyzeRequest | None = None,
    db: Session = Depends(get_db),
) -> AnalyzeResponse:
    project = _get_project_or_404(db, project_id)

    # Determine source path: from body or latest attached repository
    source = None
    if body and body.source_path:
        source = body.source_path
    else:
        repo = db.scalar(
            select(Repository)
            .where(Repository.project_id == project_id)
            .order_by(Repository.id.desc())
            .limit(1)
        )
        if repo:
            source = repo.source

    if not source:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No repository source path configured for project. Provide source_path or attach repository first.",
        )

    src_path = Path(source).resolve()
    if not src_path.exists():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Source path '{source}' does not exist on disk.",
        )

    # Execute deterministic analysis pipeline
    scan = scan_path(src_path)
    parse_result = parse_java_files(scan.root, scan.java_files)
    graph = extract_dependencies(parse_result)

    persisted = persist_analysis(
        session=db,
        scan=scan,
        parse_result=parse_result,
        graph=graph,
        project_name=project.name,
    )

    run = db.get(AnalysisRun, persisted.analysis_run_id)

    return AnalyzeResponse(
        analysis_run_id=persisted.analysis_run_id,
        project_id=persisted.project_id,
        repository_id=persisted.repository_id,
        status=run.status if run else "completed",
        file_count=run.file_count if run else len(scan.java_files),
        java_file_count=run.java_file_count if run else len(scan.java_files),
        graph_node_count=run.graph_node_count if run else len(graph.nodes),
        graph_edge_count=run.graph_edge_count if run else len(graph.edges),
    )


@router.get(
    "/{project_id}/files",
    response_model=list[FileItemResponse],
    summary="List files analyzed in latest run",
)
def list_project_files(
    project_id: int,
    limit: int = Query(500, ge=1, le=2000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> list[FileItemResponse]:
    _get_project_or_404(db, project_id)
    run = _get_latest_run_or_404(db, project_id)

    files = db.scalars(
        select(FileRecord)
        .where(FileRecord.analysis_run_id == run.id)
        .order_by(FileRecord.relative_path.asc())
        .offset(offset)
        .limit(limit)
    ).all()

    return [
        FileItemResponse(
            id=f.id,
            relative_path=f.relative_path,
            size_bytes=f.size_bytes,
            categories=list(f.categories_json or []),
        )
        for f in files
    ]


@router.get(
    "/{project_id}/classes",
    response_model=list[ClassItemResponse],
    summary="List classes extracted in latest run",
)
def list_project_classes(
    project_id: int,
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> list[ClassItemResponse]:
    _get_project_or_404(db, project_id)
    run = _get_latest_run_or_404(db, project_id)

    classes = db.scalars(
        select(ClassSymbol)
        .where(ClassSymbol.analysis_run_id == run.id)
        .order_by(ClassSymbol.name.asc())
        .offset(offset)
        .limit(limit)
    ).all()

    return [
        ClassItemResponse(
            id=c.id,
            name=c.name,
            qualified_name=c.qualified_name,
            kind=c.kind,
            start_line=c.start_line,
            end_line=c.end_line,
            modifiers=list(c.modifiers_json or []),
            annotations=list(c.annotations_json or []),
        )
        for c in classes
    ]


@router.get(
    "/{project_id}/methods",
    response_model=list[MethodItemResponse],
    summary="List methods extracted in latest run",
)
def list_project_methods(
    project_id: int,
    limit: int = Query(500, ge=1, le=2000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> list[MethodItemResponse]:
    _get_project_or_404(db, project_id)
    run = _get_latest_run_or_404(db, project_id)

    methods = db.scalars(
        select(Method)
        .where(Method.analysis_run_id == run.id)
        .order_by(Method.name.asc())
        .offset(offset)
        .limit(limit)
    ).all()

    return [
        MethodItemResponse(
            id=m.id,
            class_id=m.class_id,
            name=m.name,
            signature=m.signature,
            return_type=m.return_type,
            is_constructor=m.is_constructor,
            start_line=m.start_line,
            end_line=m.end_line,
        )
        for m in methods
    ]


@router.get(
    "/{project_id}/analysis-runs",
    response_model=list[AnalysisRunItemResponse],
    summary="List analysis runs for a project",
)
def list_project_analysis_runs(
    project_id: int,
    db: Session = Depends(get_db),
) -> list[AnalysisRunItemResponse]:
    _get_project_or_404(db, project_id)

    runs = db.scalars(
        select(AnalysisRun)
        .join(Repository, AnalysisRun.repository_id == Repository.id)
        .where(Repository.project_id == project_id)
        .order_by(AnalysisRun.id.desc())
    ).all()

    return [
        AnalysisRunItemResponse(
            id=r.id,
            repository_id=r.repository_id,
            status=r.status,
            started_at=r.started_at,
            completed_at=r.completed_at,
            file_count=r.file_count,
            java_file_count=r.java_file_count,
            graph_node_count=r.graph_node_count,
            graph_edge_count=r.graph_edge_count,
        )
        for r in runs
    ]
