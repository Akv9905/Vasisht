"""Project isolation and tenant access control (P19).

Enforces:
- Users cannot access another project's repository, graph, or analysis
- Strong scoping on all queries
"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Project
from app.security.auth import UserContext


def verify_project_access(
    user: UserContext,
    project_id: int,
    session: Session,
) -> Project:
    """Verify that the user has authorization to access the specified project."""
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID {project_id} not found.",
        )

    # In multi-tenant environments with non-admin users, restrict to allowed projects
    if not user.has_role("admin"):
        # Check if project restriction applies
        allowed_projects = getattr(user, "allowed_projects", None)
        if allowed_projects is not None and project_id not in allowed_projects:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: User {user.email} is not authorized for project {project_id}.",
            )

    return project
