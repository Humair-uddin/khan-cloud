from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.api.rbac_dependencies import require_permission
from app.db.database import get_db
from app.models.user import User
from app.schemas.network import (
    NetworkPoolRead,
    PortMappingCreate,
    PortMappingRead,
    PublicGatewayCreate,
    PublicGatewayRead,
    VPSNetworkRead,
)
from app.services.compute_service import (
    ComputeError,
    get_visible_vps,
)
from app.services.gateway_orchestration_service import (
    GatewayOrchestrationError,
    reconcile_port_mapping_if_enabled,
    reconcile_port_mapping_now,
)
from app.services.gateway_service import (
    GatewayError,
    allocate_port_mapping,
    create_public_gateway,
    get_port_mapping,
    get_public_gateway,
    list_public_gateways,
    list_vps_port_mappings,
    release_port_mapping,
)
from app.services.network_service import (
    NetworkError,
    list_network_pools,
    visible_vps_network,
)


router = APIRouter(
    prefix="/network",
    tags=["network"],
)


@router.get(
    "/pools",
    response_model=list[NetworkPoolRead],
)
def pools(
    user: User = Depends(
        require_permission("network.pools.read")
    ),
    db: Session = Depends(get_db),
):
    return list_network_pools(
        db,
        active_only=False,
    )


@router.get(
    "/gateways",
    response_model=list[PublicGatewayRead],
)
def gateways(
    user: User = Depends(
        require_permission("network.gateways.read")
    ),
    db: Session = Depends(get_db),
):
    return list_public_gateways(
        db,
        active_only=False,
    )


@router.post(
    "/gateways",
    response_model=PublicGatewayRead,
    status_code=status.HTTP_201_CREATED,
)
def create_gateway(
    payload: PublicGatewayCreate,
    user: User = Depends(
        require_permission("network.gateways.manage")
    ),
    db: Session = Depends(get_db),
):
    try:
        return create_public_gateway(
            db,
            payload=payload,
            actor=user,
        )
    except GatewayError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc


@router.get(
    "/vps/{vps_id}",
    response_model=VPSNetworkRead,
)
def vps_network(
    vps_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        vps = get_visible_vps(
            db,
            user,
            vps_id,
        )

        return visible_vps_network(
            db,
            user=user,
            vps=vps,
        )
    except (ComputeError, NetworkError) as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc


@router.get(
    "/vps/{vps_id}/ports",
    response_model=list[PortMappingRead],
)
def vps_port_mappings(
    vps_id: UUID,
    user: User = Depends(
        require_permission("vps.read")
    ),
    db: Session = Depends(get_db),
):
    try:
        vps = get_visible_vps(
            db,
            user,
            vps_id,
        )

        return list_vps_port_mappings(
            db,
            vps_id=vps.id,
            active_only=True,
        )
    except ComputeError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc


@router.post(
    "/vps/{vps_id}/ports",
    response_model=PortMappingRead,
    status_code=status.HTTP_201_CREATED,
)
def create_vps_port_mapping(
    vps_id: UUID,
    payload: PortMappingCreate,
    user: User = Depends(
        require_permission("vps.manage")
    ),
    db: Session = Depends(get_db),
):
    try:
        vps = get_visible_vps(
            db,
            user,
            vps_id,
        )

        gateway = get_public_gateway(
            db,
            payload.gateway_id,
        )

        mapping = allocate_port_mapping(
            db,
            gateway=gateway,
            vps=vps,
            protocol=payload.protocol,
            private_port=payload.private_port,
            public_port=payload.public_port,
            actor=user,
        )

        return reconcile_port_mapping_if_enabled(
            db,
            mapping=mapping,
            actor_user_id=user.id,
        )

    except ComputeError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    except GatewayError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc


@router.delete(
    "/ports/{mapping_id}",
    response_model=PortMappingRead,
)
def delete_port_mapping(
    mapping_id: UUID,
    user: User = Depends(
        require_permission("vps.manage")
    ),
    db: Session = Depends(get_db),
):
    try:
        mapping = get_port_mapping(
            db,
            mapping_id,
        )

        get_visible_vps(
            db,
            user,
            mapping.vps_instance_id,
        )

        mapping = release_port_mapping(
            db,
            mapping=mapping,
            actor=user,
        )

        return reconcile_port_mapping_if_enabled(
            db,
            mapping=mapping,
            actor_user_id=user.id,
        )

    except ComputeError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    except GatewayError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    except GatewayOrchestrationError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc


@router.post(
    "/ports/{mapping_id}/reconcile",
    response_model=PortMappingRead,
)
def reconcile_mapping(
    mapping_id: UUID,
    user: User = Depends(
        require_permission("vps.manage")
    ),
    db: Session = Depends(get_db),
):
    try:
        mapping = get_port_mapping(
            db,
            mapping_id,
        )

        get_visible_vps(
            db,
            user,
            mapping.vps_instance_id,
        )

        return reconcile_port_mapping_now(
            db,
            mapping=mapping,
            actor_user_id=user.id,
        )

    except ComputeError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    except GatewayError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    except GatewayOrchestrationError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc
