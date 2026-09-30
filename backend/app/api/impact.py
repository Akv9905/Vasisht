"""Impact analysis API endpoint (P12).

POST /projects/{project_id}/impact
GET  /projects/{project_id}/impact?target=...
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.impact import ImpactAnalysisResult, analyze_change_impact
from app.database import get_db
from app.graph.postgres import PostgresKnowledgeGraph
from app.models import AnalysisRun, Project, Repository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects", tags=["impact"])


class ImpactRequest(BaseModel):
    target: str = Field(..., min_length=1, max_length=500, description="Target symbol (e.g. PaymentService.processPayment)")
    max_depth: int = Field(5, ge=1, le=20, description="Maximum traversal depth")


class ImpactEntitySchema(BaseModel):
    id: str
    name: str
    kind: str
    file_path: str | None = None
    start_line: int | None = None
    end_line: int | None = None
    depth: int = 1
    relationship: str | None = None


class ImpactResponse(BaseModel):
    target: str
    target_kind: str
    target_file: str | None = None
    target_line: int | None = None
    direct_impact: list[dict[str, Any]]
    indirect_impact: list[dict[str, Any]]
    affected_apis: list[dict[str, Any]]
    affected_database_objects: list[dict[str, Any]]
    affected_tests: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    limitations: list[str]


def _execute_impact_analysis(
    session: Session,
    project_id: int,
    target: str,
    max_depth: int = 5,
) -> ImpactResponse:
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID {project_id} not found.",
        )

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

    kg = PostgresKnowledgeGraph(session, run.id)
    graph = kg.load_graph()
    result = analyze_change_impact(graph, target_symbol=target, max_depth=max_depth)

    return ImpactResponse(
        target=result.target,
        target_kind=result.target_kind,
        target_file=result.target_file,
        target_line=result.target_line,
        direct_impact=result.direct_impact,
        indirect_impact=result.indirect_impact,
        affected_apis=result.affected_apis,
        affected_database_objects=result.affected_database_objects,
        affected_tests=result.affected_tests,
        evidence=result.evidence,
        limitations=result.limitations,
    )


@router.get(
    "/{project_id}/impact",
    response_model=ImpactResponse,
    summary="Run change-impact analysis for a symbol (GET)",
)
def get_impact(
    project_id: int,
    target: str = Query(..., description="Target symbol e.g. PaymentService.processPayment"),
    max_depth: int = Query(5, ge=1, le=20),
    db: Session = Depends(get_db),
) -> ImpactResponse:
    return _execute_impact_analysis(db, project_id, target, max_depth)


@router.post(
    "/{project_id}/impact",
    response_model=ImpactResponse,
    summary="Run change-impact analysis for a symbol (POST)",
)
def post_impact(
    project_id: int,
    body: ImpactRequest,
    db: Session = Depends(get_db),
) -> ImpactResponse:
    return _execute_impact_analysis(db, project_id, body.target, body.max_depth)
