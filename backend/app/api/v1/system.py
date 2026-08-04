from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.core.config import settings
from app.db.database import SessionLocal

router = APIRouter(tags=["system"])


def _configured_version() -> str:
    return str(settings.APP_VERSION)


def _environment() -> str:
    return str(getattr(settings, "APP_ENV", "unknown"))


@router.get(
    "/ready",
    summary="Readiness probe",
    description=(
        "Reports whether the control plane is ready to receive traffic. "
        "Readiness requires a successful database query."
    ),
)
def readiness(response: Response) -> dict[str, Any]:
    checked_at = datetime.now(UTC).isoformat()

    try:
        with SessionLocal() as session:
            session.execute(text("SELECT 1"))
        database = "connected"
        ready = True
    except Exception:
        database = "disconnected"
        ready = False
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "ready": ready,
        "database": database,
        "version": _configured_version(),
        "environment": _environment(),
        "checked_at": checked_at,
    }


@router.get(
    "/version",
    summary="Control-plane version",
    description="Returns machine-readable Khan Cloud control-plane build information.",
)
def version() -> dict[str, str]:
    return {
        "product": str(getattr(settings, "APP_NAME", "Khan Cloud")),
        "version": _configured_version(),
        "environment": _environment(),
        "api_version": "v1",
        "component": "control-plane",
    }
