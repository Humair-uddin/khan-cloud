from fastapi import FastAPI
from app.core.config import settings
from app.db.database import check_database

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Khan Cloud Control Plane"
)

@app.get("/")
def root():
    return {
        "product": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.APP_ENV,
        "control_plane": "KC-CP-01",
        "status": "running"
    }

@app.get("/health")
def health():
    db_status = "connected"
    try:
        check_database()
    except Exception as e:
        db_status = f"error: {str(e)}"

    return {
        "status": "healthy",
        "database": db_status,
        "version": settings.APP_VERSION
    }
