"""Request flow tracing API endpoint (P11).

Endpoints:
  GET  /projects/{project_id}/request-flow?endpoint=...
  POST /projects/{project_id}/request-flow
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.graph.postgres import PostgresKnowledgeGraph
from app.graph.traversal import RequestFlowResult, trace_request_flow
from app.models import AnalysisRun, Project, Repository
from app.retrieval import StructuredRetriever

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects", tags=["request-flow"])


class RequestFlowQueryRequest(BaseModel):
    endpoint: str = Field(..., min_length=1, max_length=500, description="HTTP endpoint or path to trace")


class RequestFlowStepSchema(BaseModel):
    step: int
    entity: str
    role: str
    source_file: str | None = None
    method: str | None = None
    relationship: str | None = None
    resolved: bool = True
    evidence: dict[str, Any] = Field(default_factory=dict)


class RequestFlowResponse(BaseModel):
    endpoint: str
    reaches_database: bool
    database_table: str | None = None
    steps: list[RequestFlowStepSchema]
    unresolved_steps: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


def _execute_flow_tracing(session: Session, project_id: int, endpoint: str) -> RequestFlowResponse:
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID {project_id} not found.",
        )

    # Find latest completed run for this project
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
    flow_result: RequestFlowResult = trace_request_flow(graph, endpoint)

    steps: list[RequestFlowStepSchema] = []
    for s in flow_result.steps:
        # Determine method and entity
        method_name = s.node_name if s.node_kind == "method" else None
        details = dict(s.details or {})
        start_line = details.get("start_line")
        end_line = details.get("end_line")

        evidence = {
            "node_id": s.node_id,
            "qualified_name": s.qualified_name,
            "start_line": start_line,
            "end_line": end_line,
            "annotations": details.get("annotations", []),
        }

        steps.append(
            RequestFlowStepSchema(
                step=s.step_number,
                entity=s.node_name,
                role=s.node_kind.capitalize(),
                source_file=s.file_path,
                method=method_name,
                relationship=s.relationship,
                resolved=True,
                evidence=evidence,
            )
        )

    limitations = [
        "Static call graph analysis; runtime reflection or dynamic proxies are not resolved.",
    ]
    if flow_result.unresolved_steps:
        limitations.append(f"Unresolved calls encountered: {', '.join(flow_result.unresolved_steps)}")

    return RequestFlowResponse(
        endpoint=endpoint,
        reaches_database=flow_result.reaches_database,
        database_table=flow_result.database_table,
        steps=steps,
        unresolved_steps=flow_result.unresolved_steps,
        limitations=limitations,
    )


@router.get(
    "/{project_id}/request-flow",
    response_model=RequestFlowResponse,
    summary="Trace request flow for an endpoint (GET)",
)
def get_request_flow(
    project_id: int,
    endpoint: str = Query(..., description="Endpoint path e.g. /api/payment"),
    db: Session = Depends(get_db),
) -> RequestFlowResponse:
    return _execute_flow_tracing(db, project_id, endpoint)


@router.post(
    "/{project_id}/request-flow",
    response_model=RequestFlowResponse,
    summary="Trace request flow for an endpoint (POST)",
)
def post_request_flow(
    project_id: int,
    body: RequestFlowQueryRequest,
    db: Session = Depends(get_db),
) -> RequestFlowResponse:
    return _execute_flow_tracing(db, project_id, body.endpoint)
