"""FastAPI application entrypoint."""

from fastapi import FastAPI

from app.api.architecture import router as architecture_router
from app.api.flow import router as flow_router
from app.api.health import router as health_router
from app.api.impact import router as impact_router
from app.api.modernization import router as modernization_router
from app.api.projects import router as projects_router
from app.api.questions import router as questions_router
from app.api.reports import router as reports_router
from app.api.risks import router as risks_router
from app.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Legacy Java/Spring software intelligence platform (Phase 1).",
)

app.include_router(health_router)
app.include_router(projects_router)
app.include_router(questions_router)
app.include_router(flow_router)
app.include_router(impact_router)
app.include_router(risks_router)
app.include_router(architecture_router)
app.include_router(modernization_router)
app.include_router(reports_router)


@app.get("/")
def root() -> dict[str, str]:
    return {
        "name": settings.app_name,
        "version": "0.1.0",
        "mode": "local/free",
        "docs": "/docs",
        "health": "/health",
    }
