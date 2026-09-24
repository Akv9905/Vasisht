"""FastAPI application entrypoint."""

from fastapi import FastAPI

from app.api.health import router as health_router
from app.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Legacy Java/Spring software intelligence platform (Phase 1).",
)

app.include_router(health_router)


@app.get("/")
def root() -> dict[str, str]:
    return {
        "name": settings.app_name,
        "version": "0.1.0",
        "mode": "local/free",
        "docs": "/docs",
        "health": "/health",
    }
