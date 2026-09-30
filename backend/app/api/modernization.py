"""Modernization analysis API endpoint (P15 & P17).

GET /projects/{project_id}/modernization
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.modernization import ModernizationReport, analyze_modernization
from app.database import get_db
from app.graph.postgres import PostgresKnowledgeGraph
from app.models import AnalysisRun, Project, Repository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects", tags=["modernization"])


class ModernizationFindingSchema(BaseModel):
    category: str
    finding: str
    evidence: list[str]
    reason: str
    possible_direction: str
    dependencies: list[str]
    risk_considerations: list[str]
    suggested_investigation_order: int
    limitations: list[str]


class ModernizationReportResponse(BaseModel):
    total_findings: int
    findings: list[ModernizationFindingSchema]


@router.get(
    "/{project_id}/modernization",
    response_model=ModernizationReportResponse,
    summary="Get evidence-backed modernization findings for a project",
)
def get_project_modernization(
    project_id: int,
    db: Session = Depends(get_db),
) -> ModernizationReportResponse:
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
    report: ModernizationReport = analyze_modernization(graph)

    return ModernizationReportResponse(
        total_findings=report.total_findings,
        findings=[
            ModernizationFindingSchema(
                category=f.category,
                finding=f.finding,
                evidence=f.evidence,
                reason=f.reason,
                possible_direction=f.possible_direction,
                dependencies=f.dependencies,
                risk_considerations=f.risk_considerations,
                suggested_investigation_order=f.suggested_investigation_order,
                limitations=f.limitations,
            )
            for f in report.findings
        ],
    )
