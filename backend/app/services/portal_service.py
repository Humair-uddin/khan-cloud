from sqlalchemy.orm import Session

from app.models.user import User
from app.schemas.portal import (
    PortalPublicEndpointRead,
    PortalSummaryRead,
    PortalVPSRead,
)
from app.services.compute_service import visible_vps
from app.services.gateway_service import (
    get_public_gateway,
    list_vps_port_mappings,
)
from app.services.network_service import visible_vps_network


def customer_portal_summary(
    db: Session,
    user: User,
) -> PortalSummaryRead:
    rows = [
        v
        for v in visible_vps(db, user)
        if v.status != "deleted"
    ]

    items: list[PortalVPSRead] = []

    for vps in rows:
        net = visible_vps_network(
            db,
            user=user,
            vps=vps,
        )

        public_endpoints: list[PortalPublicEndpointRead] = []

        for mapping in list_vps_port_mappings(
            db,
            vps_id=vps.id,
            active_only=True,
        ):
            gateway = get_public_gateway(
                db,
                mapping.gateway_id,
            )

            public_endpoints.append(
                PortalPublicEndpointRead(
                    protocol=mapping.protocol,
                    public_ip=gateway.public_ip,
                    public_port=mapping.public_port,
                    private_port=mapping.private_port,
                )
            )

        items.append(
            PortalVPSRead(
                id=vps.id,
                name=vps.name,
                image=vps.image,
                status=vps.status,
                desired_state=vps.desired_state,
                vcpu=vps.vcpu,
                memory_bytes=vps.memory_bytes,
                disk_bytes=vps.disk_bytes,
                primary_ip=vps.primary_ip,
                private_addresses=net.private_addresses,
                public_addresses=net.public_addresses,
                public_endpoints=public_endpoints,
                access_username=vps.access_username,
                ssh_public_key_fingerprint=(
                    vps.ssh_public_key_fingerprint
                ),
                guest_ready_at=vps.guest_ready_at,
            )
        )

    return PortalSummaryRead(
        vps_total=len(items),
        vps_running=sum(
            1 for x in items if x.status == "running"
        ),
        vps_stopped=sum(
            1 for x in items if x.status == "stopped"
        ),
        vps_provisioning=sum(
            1 for x in items if x.status == "provisioning"
        ),
        vps=items,
    )
