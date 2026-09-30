"""Architecture and graph visualization API endpoints (P14 & P17).

GET /projects/{project_id}/architecture
GET /projects/{project_id}/graph
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.architecture import build_architecture_view, build_graph_visualization
from app.database import get_db
from app.graph.postgres import PostgresKnowledgeGraph
from app.models import AnalysisRun, Project, Repository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects", tags=["architecture"])


class ArchitectureResponse(BaseModel):
    packages: list[dict[str, Any]]
    modules: list[dict[str, Any]]
    controllers: list[dict[str, Any]]
    services: list[dict[str, Any]]
    repositories: list[dict[str, Any]]
    databases: list[dict[str, Any]]
    apis: list[dict[str, Any]]
    external_integrations: list[dict[str, Any]]
    tests: list[dict[str, Any]]
    chains: list[dict[str, Any]]


class GraphResponse(BaseModel):
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    categories: dict[str, int]
    total_nodes: int
    total_edges: int


def _load_project_graph(session: Session, project_id: int):
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
    return kg.load_graph()


@router.get(
    "/{project_id}/architecture",
    response_model=ArchitectureResponse,
    summary="Get architectural component breakdown for a project",
)
def get_architecture(
    project_id: int,
    db: Session = Depends(get_db),
) -> ArchitectureResponse:
    graph = _load_project_graph(db, project_id)
    arch = build_architecture_view(graph)
    return ArchitectureResponse(
        packages=arch.packages,
        modules=arch.modules,
        controllers=arch.controllers,
        services=arch.services,
        repositories=arch.repositories,
        databases=arch.databases,
        apis=arch.apis,
        external_integrations=arch.external_integrations,
        tests=arch.tests,
        chains=arch.chains,
    )


@router.get(
    "/{project_id}/graph",
    response_model=GraphResponse,
    summary="Get graph visualization nodes and edges for a project",
)
def get_graph(
    project_id: int,
    categories: list[str] | None = Query(None, description="Optional categories to filter by"),
    db: Session = Depends(get_db),
) -> GraphResponse:
    graph = _load_project_graph(db, project_id)
    viz = build_graph_visualization(graph, category_filter=categories)
    return GraphResponse(
        nodes=viz["nodes"],
        edges=viz["edges"],
        categories=viz["categories"],
        total_nodes=viz["total_nodes"],
        total_edges=viz["total_edges"],
    )
