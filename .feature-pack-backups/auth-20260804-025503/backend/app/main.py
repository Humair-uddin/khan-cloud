from fastapi import FastAPI

from app.api.v1.router import api_router
from app.core.config import settings
from app.db.database import check_database

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Khan Cloud Control Plane",
)

app.include_router(api_router, prefix=settings.API_PREFIX)


@app.get("/")
def root() -> dict[str, str]:
    return {
        "product": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.APP_ENV,
        "control_plane": "KC-CP-01",
        "status": "running",
    }


@app.get("/health")
def health() -> dict[str, str]:
    try:
        check_database()
        database = "connected"
        status = "healthy"
    except Exception:
        database = "disconnected"
        status = "degraded"

    return {
        "status": status,
        "database": database,
        "version": settings.APP_VERSION,
    }
