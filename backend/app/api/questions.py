"""Questions API endpoints (P10).

POST /projects/{project_id}/questions
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.analysis.qa import CodebaseQAEngine
from app.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects", tags=["questions"])


class QuestionRequest(BaseModel):
    """User question payload."""

    question: str = Field(..., min_length=1, max_length=1000, description="Question about codebase architecture")


class FlowStepSchema(BaseModel):
    step: int
    role: str
    symbol: str
    file_path: str
    start_line: int | None = None
    end_line: int | None = None
    relationship_to_next: str | None = None


class EvidenceItemSchema(BaseModel):
    type: str
    symbol: str
    file_path: str
    start_line: int | None = None
    end_line: int | None = None
    relationship: str | None = None
    details: Any = None


class QuestionResponse(BaseModel):
    """Grounded evidence-backed answer."""

    answer: str
    evidence: list[EvidenceItemSchema]
    flow: list[FlowStepSchema]
    limitations: list[str]


@router.post(
    "/{project_id}/questions",
    response_model=QuestionResponse,
    status_code=status.HTTP_200_OK,
    summary="Ask an evidence-backed question about a project's codebase",
)
def ask_project_question(
    project_id: int,
    body: QuestionRequest,
    db: Session = Depends(get_db),
) -> QuestionResponse:
    """Answer a developer question using structured, graph, and optional semantic retrieval."""
    try:
        engine = CodebaseQAEngine(session=db, project_id=project_id)
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    try:
        result = engine.answer(body.question)
        return QuestionResponse(
            answer=result.answer,
            evidence=[EvidenceItemSchema(**ev) for ev in result.evidence],
            flow=[FlowStepSchema(**s) for s in result.flow],
            limitations=result.limitations,
        )
    except Exception as e:
        logger.exception("Unexpected error in ask_project_question: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while answering the question.",
        )
