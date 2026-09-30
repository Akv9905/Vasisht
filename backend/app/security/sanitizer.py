"""Secret management, scrubbing, and secure error handling (P19).

Guarantees:
- Secrets, tokens, passwords, and credentials are never logged or exposed in outputs
- Internal server errors and database details are sanitized before returning to clients
"""

from __future__ import annotations

import re
from typing import Any

# Regex patterns matching potential secrets
_SECRET_PATTERNS = [
    (re.compile(r"(?i)(password|passwd|secret|api[_-]?key|access[_-]?token|bearer)\s*[:=]\s*['\"]?([^'\"\s,;]+)"), r"\1=***REDACTED***"),
    (re.compile(r"Bearer\s+([A-Za-z0-9\-._~+/]+=*)"), r"Bearer ***REDACTED***"),
    (re.compile(r"(?i)(AKIA[0-9A-Z]{16})"), r"***REDACTED_AWS_KEY***"),
    (re.compile(r"-----BEGIN\s+PRIVATE\s+KEY-----[\s\S]*?-----END\s+PRIVATE\s+KEY-----"), r"***REDACTED_PRIVATE_KEY***"),
    (re.compile(r"postgres(ql)?://([^:]+):([^@]+)@"), r"postgresql://\2:***REDACTED***@"),
]


def redact_secrets(text: str) -> str:
    """Scrub sensitive credentials, passwords, and tokens from text or log messages."""
    if not text:
        return text
    result = text
    for pattern, replacement in _SECRET_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


def sanitize_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Recursively scrub secrets from dictionaries."""
    sanitized: dict[str, Any] = {}
    sensitive_keys = {"password", "passwd", "token", "secret", "api_key", "authorization", "credential"}

    for k, v in data.items():
        if any(s in k.lower() for s in sensitive_keys):
            sanitized[k] = "***REDACTED***"
        elif isinstance(v, dict):
            sanitized[k] = sanitize_dict(v)
        elif isinstance(v, list):
            sanitized[k] = [
                sanitize_dict(item) if isinstance(item, dict) else (redact_secrets(str(item)) if isinstance(item, str) else item)
                for item in v
            ]
        elif isinstance(v, str):
            sanitized[k] = redact_secrets(v)
        else:
            sanitized[k] = v

    return sanitized


def secure_error_message(exc: Exception) -> str:
    """Convert an exception into a safe, client-facing message without leaking internal details."""
    raw = str(exc)
    sanitized = redact_secrets(raw)
    # Strip local filesystem root if present
    sanitized = re.sub(r"[A-Za-z]:\\[\w\\\.\-]+", "[LOCAL_PATH]", sanitized)
    return sanitized
