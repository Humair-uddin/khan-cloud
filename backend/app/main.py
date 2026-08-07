from fastapi import FastAPI

from app.api.v1.deployment_profiles import router as deployment_profiles_router
from app.api.v1.audit import router as audit_router
from app.api.v1.auth import router as auth_router
from app.api.v1.nodes import router as nodes_router
from app.api.v1.rbac import router as rbac_router
from app.api.v1.system import router as system_router
from app.api.v1.organizations import router as organizations_router
from app.api.v1.support import router as support_router
from app.api.v1.operations import router as operations_router
from app.core.config import settings
from app.db.database import check_database

app=FastAPI(title=settings.APP_NAME,version=settings.APP_VERSION,description="Khan Cloud Control Plane")
app.include_router(auth_router,prefix=settings.API_PREFIX)
app.include_router(rbac_router,prefix=settings.API_PREFIX)
app.include_router(nodes_router,prefix=settings.API_PREFIX)
app.include_router(audit_router,prefix=settings.API_PREFIX)
app.include_router(system_router)
app.include_router(organizations_router,prefix=settings.API_PREFIX)
app.include_router(support_router,prefix=settings.API_PREFIX)
app.include_router(operations_router,prefix=settings.API_PREFIX)

@app.get("/")
def root():
    return {"product":settings.APP_NAME,"version":settings.APP_VERSION,"environment":settings.APP_ENV,
            "control_plane":"KC-CP-01","status":"running"}

@app.get("/health")
def health():
    try: check_database(); database="connected"; service_status="healthy"
    except Exception: database="disconnected"; service_status="degraded"
    return {"status":service_status,"database":database,"version":settings.APP_VERSION}

app.include_router(deployment_profiles_router, prefix=settings.API_PREFIX)
