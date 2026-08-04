from fastapi import FastAPI

from app.api.v1.auth import router as auth_router
from app.core.config import settings
from app.db.database import check_database

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Khan Cloud Control Plane",
)

# Register feature routers directly with the FastAPI application.
app.include_router(
    auth_router,
    prefix=settings.API_PREFIX,
)


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
        service_status = "healthy"
    except Exception:
        database = "disconnected"
        service_status = "degraded"

    return {
        "status": service_status,
        "database": database,
        "version": settings.APP_VERSION,
    }
