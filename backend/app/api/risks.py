"""Technical risk analysis API endpoint (P13 & P17).

GET /projects/{project_id}/risks
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.risks import RiskReport, analyze_risks
from app.database import get_db
from app.graph.postgres import PostgresKnowledgeGraph
from app.models import AnalysisRun, Project, Repository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects", tags=["risks"])


class RiskFindingSchema(BaseModel):
    finding_type: str
    severity: str
    subject: str
    summary: str
    metrics: dict[str, Any]
    evidence: list[str]


class RiskReportResponse(BaseModel):
    total_findings: int
    high_count: int
    medium_count: int
    low_count: int
    findings: list[RiskFindingSchema]


@router.get(
    "/{project_id}/risks",
    response_model=RiskReportResponse,
    summary="Get deterministic technical-risk indicators for a project",
)
def get_project_risks(
    project_id: int,
    db: Session = Depends(get_db),
) -> RiskReportResponse:
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
    report: RiskReport = analyze_risks(parse_result=None, graph=graph)

    return RiskReportResponse(
        total_findings=report.total_findings,
        high_count=report.high_count,
        medium_count=report.medium_count,
        low_count=report.low_count,
        findings=[
            RiskFindingSchema(
                finding_type=f.finding_type,
                severity=f.severity,
                subject=f.subject,
                summary=f.summary,
                metrics=f.metrics,
                evidence=f.evidence,
            )
            for f in report.findings
        ],
    )
