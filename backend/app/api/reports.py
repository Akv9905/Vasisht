"""Reports generation API endpoint (P16 & P17).

POST /projects/{project_id}/reports
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.graph.postgres import PostgresKnowledgeGraph
from app.ingestion.scanner import ScanResult
from app.models import AnalysisRun, Project, Repository
from app.reports.generator import generate_json_report, generate_markdown_report

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects", tags=["reports"])


class ReportRequest(BaseModel):
    format: str = Field("markdown", description="Report format: 'markdown' or 'json'")


class ReportResponse(BaseModel):
    format: str
    content: str | dict[str, Any]
    generated_at: str


@router.post(
    "/{project_id}/reports",
    response_model=ReportResponse,
    summary="Generate an 11-section Markdown or JSON report for a project",
)
def generate_project_report(
    project_id: int,
    body: ReportRequest,
    db: Session = Depends(get_db),
) -> ReportResponse:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID {project_id} not found.",
        )

    run = db.scalar(
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

    kg = PostgresKnowledgeGraph(db, run.id)
    graph = kg.load_graph()

    repo = db.get(Repository, run.repository_id)
    repo_source = repo.source if repo else f"project-{project_id}"

    # Construct ScanResult from stored analysis run counts
    scan = ScanResult(
        source=repo_source,
        root=repo_source,
        total_files=run.file_count or len(graph.find_nodes(kind="file")),
        java_files=[n.file_path for n in graph.nodes if n.kind == "class" and n.file_path],
    )

    fmt = body.format.lower().strip()
    if fmt == "json":
        raw_json = generate_json_report(scan, parse_result=None, graph=graph)
        parsed_content = json.loads(raw_json)
        return ReportResponse(
            format="json",
            content=parsed_content,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
    else:
        md_text = generate_markdown_report(scan, parse_result=None, graph=graph)
        return ReportResponse(
            format="markdown",
            content=md_text,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
