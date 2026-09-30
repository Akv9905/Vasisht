"""Authentication and authorization abstraction (P19).

Supports:
- Local/free developer mode by default (zero external cloud dependencies)
- Token/API Key authentication adapter
- Role-based authorization
- Secure token inspection without logging credentials
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import hmac
import os
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User


@dataclass
class UserContext:
    user_id: int
    email: str
    roles: list[str] = field(default_factory=lambda: ["viewer", "analyst"])
    is_authenticated: bool = True

    def has_role(self, role: str) -> bool:
        return role in self.roles or "admin" in self.roles


class AuthProvider(ABC):
    @abstractmethod
    def authenticate(self, token: str | None, session: Session) -> UserContext:
        """Authenticate user from token/credentials."""
        pass


class LocalAuthProvider(AuthProvider):
    """Default local authentication provider requiring no cloud or third-party service."""

    def authenticate(self, token: str | None, session: Session) -> UserContext:
        # In local-first mode, if an API key is configured via ENV, verify it constant-time
        expected_key = os.getenv("APP_API_KEY")
        if expected_key:
            if not token:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required: missing API key.",
                )
            # Constant-time comparison to prevent timing attacks
            if not hmac.compare_digest(token.strip(), expected_key.strip()):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Invalid API key provided.",
                )

        # Return local analyst/admin user context
        return UserContext(
            user_id=1,
            email="local-analyst@localhost",
            roles=["admin", "analyst", "viewer"],
            is_authenticated=True,
        )


class TokenAuthProvider(AuthProvider):
    """Database-backed token or static token authentication provider."""

    def __init__(self, valid_tokens: dict[str, UserContext] | None = None) -> None:
        self.valid_tokens = valid_tokens or {}

    def authenticate(self, token: str | None, session: Session) -> UserContext:
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing authorization token.",
            )

        clean_token = token.replace("Bearer ", "").strip()
        if clean_token in self.valid_tokens:
            return self.valid_tokens[clean_token]

        # Check DB user if applicable
        db_user = session.query(User).filter(User.password_hash == clean_token).first()
        if db_user and db_user.is_active:
            return UserContext(
                user_id=db_user.id,
                email=db_user.email,
                roles=list(db_user.roles_json or ["viewer"]),
                is_authenticated=True,
            )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authorization token.",
        )


_DEFAULT_AUTH_PROVIDER: AuthProvider = LocalAuthProvider()


def get_auth_provider() -> AuthProvider:
    return _DEFAULT_AUTH_PROVIDER


def set_auth_provider(provider: AuthProvider) -> None:
    global _DEFAULT_AUTH_PROVIDER
    _DEFAULT_AUTH_PROVIDER = provider


def get_current_user(
    authorization: str | None = Header(None),
    x_api_key: str | None = Header(None),
    db: Session = Depends(get_db),
    provider: AuthProvider = Depends(get_auth_provider),
) -> UserContext:
    """FastAPI dependency to extract and authenticate current user."""
    token = x_api_key or (authorization.replace("Bearer ", "") if authorization else None)
    return provider.authenticate(token, db)


def require_role(required_role: str):
    """FastAPI dependency factory enforcing role-based access control."""

    def role_checker(user: UserContext = Depends(get_current_user)) -> UserContext:
        if not user.has_role(required_role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: role '{required_role}' required.",
            )
        return user

    return role_checker
