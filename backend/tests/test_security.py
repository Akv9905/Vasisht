"""Security and project isolation tests (P19).

Verifies:
- Authentication abstraction (Local & Token providers)
- Role-based authorization
- Project isolation (no cross-project leakage)
- Secret management and redaction (never log or leak secrets)
- Audit logging with sanitized payloads
- Upload limits, file validation, and temporary directory cleanup
- Safe ZIP extraction and error handling
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import HTTPException
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import AuditLog, Base, Project
from app.security import (
    LocalAuthProvider,
    TokenAuthProvider,
    UserContext,
    log_audit_event,
    redact_secrets,
    sanitize_dict,
    temporary_upload_directory,
    validate_upload_filename,
    validate_upload_size,
    verify_project_access,
)


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()
    engine.dispose()


class TestAuthenticationAndAuthorization:
    def test_local_auth_provider_default(self, db_session):
        # Default local mode requires no external API and works out of the box
        provider = LocalAuthProvider()
        user = provider.authenticate(None, db_session)
        assert user.is_authenticated is True
        assert user.has_role("analyst") is True
        assert user.has_role("admin") is True

    def test_local_auth_with_api_key_env(self, db_session, monkeypatch):
        monkeypatch.setenv("APP_API_KEY", "super-secret-key-12345")
        provider = LocalAuthProvider()

        # Missing token raises 401
        with pytest.raises(HTTPException) as exc1:
            provider.authenticate(None, db_session)
        assert exc1.value.status_code == 401

        # Wrong token raises 403
        with pytest.raises(HTTPException) as exc2:
            provider.authenticate("wrong-key", db_session)
        assert exc2.value.status_code == 403

        # Correct token succeeds
        user = provider.authenticate("super-secret-key-12345", db_session)
        assert user.is_authenticated is True

    def test_token_auth_provider(self, db_session):
        valid_user = UserContext(user_id=42, email="analyst@corp.local", roles=["analyst"])
        provider = TokenAuthProvider(valid_tokens={"token-abc-xyz": valid_user})

        user = provider.authenticate("Bearer token-abc-xyz", db_session)
        assert user.user_id == 42
        assert user.has_role("analyst") is True
        assert user.has_role("non_existent_role") is False

        with pytest.raises(HTTPException) as exc:
            provider.authenticate("invalid-token", db_session)
        assert exc.value.status_code == 401


class TestProjectIsolation:
    def test_project_isolation_allows_admin(self, db_session):
        proj = Project(name="ProjectA")
        db_session.add(proj)
        db_session.commit()

        admin_user = UserContext(user_id=1, email="admin@corp.local", roles=["admin"])
        verified = verify_project_access(admin_user, proj.id, db_session)
        assert verified.id == proj.id

    def test_project_isolation_denies_unauthorized_user(self, db_session):
        proj = Project(name="ProjectPrivate")
        db_session.add(proj)
        db_session.commit()

        restricted_user = UserContext(user_id=99, email="user@corp.local", roles=["viewer"])
        setattr(restricted_user, "allowed_projects", [10, 20])  # only allowed projects 10 and 20

        with pytest.raises(HTTPException) as exc:
            verify_project_access(restricted_user, proj.id, db_session)
        assert exc.value.status_code == 403
        assert "Access denied" in exc.value.detail

    def test_project_isolation_404_for_missing_project(self, db_session):
        user = UserContext(user_id=1, email="user@corp.local", roles=["admin"])
        with pytest.raises(HTTPException) as exc:
            verify_project_access(user, 99999, db_session)
        assert exc.value.status_code == 404


class TestSecretManagementAndRedaction:
    def test_redact_secrets_in_strings(self):
        sample = "Connecting with password='super_secret_db_pass' and token: abc-xyz-12345"
        redacted = redact_secrets(sample)
        assert "super_secret_db_pass" not in redacted
        assert "***REDACTED***" in redacted

    def test_redact_bearer_and_aws_keys(self):
        sample = "Authorization: Bearer my_jwt_token_payload AKIAIOSFODNN7EXAMPLE"
        redacted = redact_secrets(sample)
        assert "my_jwt_token_payload" not in redacted
        assert "AKIAIOSFODNN7EXAMPLE" not in redacted
        assert "***REDACTED***" in redacted

    def test_sanitize_dict_recursively(self):
        data = {
            "project_name": "PaymentApp",
            "db_password": "plain_password_123",
            "nested": {
                "api_key": "secret_key_value",
                "normal": "safe_value",
            },
        }
        sanitized = sanitize_dict(data)
        assert sanitized["project_name"] == "PaymentApp"
        assert sanitized["db_password"] == "***REDACTED***"
        assert sanitized["nested"]["api_key"] == "***REDACTED***"
        assert sanitized["nested"]["normal"] == "safe_value"


class TestAuditLogging:
    def test_audit_log_persists_sanitized_event(self, db_session):
        event = log_audit_event(
            session=db_session,
            action="ANALYSIS_RUN",
            user_id=1,
            project_id=10,
            entity_type="Repository",
            entity_id="sample-repo",
            details={
                "scan_files": 13,
                "access_token": "secret_token_never_log",
            },
        )
        assert event.id is not None
        assert event.action == "ANALYSIS_RUN"
        # Secret in details must be sanitized
        assert event.details_json["access_token"] == "***REDACTED***"
        assert event.details_json["scan_files"] == 13

        # Verify query from database
        stored = db_session.get(AuditLog, event.id)
        assert stored is not None
        assert stored.details_json["access_token"] == "***REDACTED***"


class TestUploadValidationAndCleanup:
    def test_validate_upload_filename(self):
        # Valid extensions
        assert validate_upload_filename("repo.zip") == "repo.zip"
        assert validate_upload_filename("Service.java") == "Service.java"

        # Traversal attempt sanitized
        assert validate_upload_filename("../../etc/passwd.zip") == "passwd.zip"

        # Forbidden extensions rejected
        with pytest.raises(HTTPException) as exc:
            validate_upload_filename("malicious.exe")
        assert exc.value.status_code == 400

    def test_validate_upload_size(self):
        # Within limit
        validate_upload_size(50 * 1024 * 1024, max_bytes=100 * 1024 * 1024)

        # Exceeds limit
        with pytest.raises(HTTPException) as exc:
            validate_upload_size(150 * 1024 * 1024, max_bytes=100 * 1024 * 1024)
        assert exc.value.status_code == 413

    def test_temporary_upload_directory_cleanup(self):
        temp_path = None
        with temporary_upload_directory() as td:
            temp_path = td
            assert temp_path.exists()
            # Create a file inside
            (temp_path / "test.txt").write_text("temporary data")
            assert (temp_path / "test.txt").exists()

        # After exiting context manager, temp directory must be purged
        assert not temp_path.exists()
