"""Audit logging service (P19).

Persists immutable security audit logs for:
- User logins / token authentications
- Repository analysis executions
- Report generations
- Questions and intelligence queries
- Access violations and unauthorized requests
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditLog
from app.security.sanitizer import sanitize_dict

logger = logging.getLogger(__name__)


def log_audit_event(
    session: Session,
    action: str,
    user_id: int | None = None,
    project_id: int | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> AuditLog:
    """Record a sanitized security audit log entry in PostgreSQL."""
    clean_details = sanitize_dict(details or {})

    entry = AuditLog(
        user_id=user_id,
        project_id=project_id,
        action=action[:100],
        entity_type=entity_type[:100] if entity_type else None,
        entity_id=str(entity_id) if entity_id else None,
        details_json=clean_details,
    )
    session.add(entry)
    session.commit()
    session.refresh(entry)

    logger.info(
        "AUDIT: action=%s user=%s project=%s entity=%s/%s",
        action,
        user_id,
        project_id,
        entity_type,
        entity_id,
    )
    return entry
