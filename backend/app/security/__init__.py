"""Security package (P19).

Exports:
- Authentication & Authorization
- Project Isolation
- Secret Management & Scrubbing
- Audit Logging
- Safe Uploads & Temporary File Cleanup
"""

from __future__ import annotations

from app.security.audit import log_audit_event
from app.security.auth import (
    AuthProvider,
    LocalAuthProvider,
    TokenAuthProvider,
    UserContext,
    get_auth_provider,
    get_current_user,
    require_role,
    set_auth_provider,
)
from app.security.isolation import verify_project_access
from app.security.sanitizer import (
    redact_secrets,
    sanitize_dict,
    secure_error_message,
)
from app.security.upload import (
    DEFAULT_MAX_UPLOAD_BYTES,
    temporary_upload_directory,
    validate_upload_filename,
    validate_upload_size,
)

__all__ = [
    "AuthProvider",
    "LocalAuthProvider",
    "TokenAuthProvider",
    "UserContext",
    "get_auth_provider",
    "set_auth_provider",
    "get_current_user",
    "require_role",
    "verify_project_access",
    "log_audit_event",
    "redact_secrets",
    "sanitize_dict",
    "secure_error_message",
    "DEFAULT_MAX_UPLOAD_BYTES",
    "validate_upload_filename",
    "validate_upload_size",
    "temporary_upload_directory",
]
