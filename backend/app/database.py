"""Database engine and session helpers."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings


def make_engine(database_url: str | None = None, **kwargs: object) -> Engine:
    """Create an engine for the configured database (PostgreSQL by default)."""
    url = database_url or get_settings().database_url
    if url.startswith("sqlite"):
        kwargs.setdefault("connect_args", {"check_same_thread": False})
    return create_engine(url, pool_pre_ping=True, **kwargs)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create a session factory bound to an engine."""
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@contextmanager
def session_scope(database_url: str | None = None) -> Iterator[Session]:
    """Yield a transaction-scoped session and dispose its short-lived engine."""
    engine = make_engine(database_url)
    factory = make_session_factory(engine)
    try:
        with factory.begin() as session:
            yield session
    finally:
        engine.dispose()


def get_db() -> Iterator[Session]:
    """FastAPI dependency for database session."""
    engine = make_engine()
    factory = make_session_factory(engine)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
