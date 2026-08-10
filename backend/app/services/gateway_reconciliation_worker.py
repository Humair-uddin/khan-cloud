from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.gateway import PortMapping
from app.services.gateway_orchestration_service import (
    GatewayOrchestrationError,
    reconcile_port_mapping_now,
)


@dataclass(frozen=True)
class GatewayReconciliationBatchResult:
    selected: int
    succeeded: int
    failed: int
    mapping_ids: tuple[UUID, ...]


def claim_next_reconciliation_candidate(
    db: Session,
) -> PortMapping | None:
    """
    Claim one reconciliation candidate.

    The row lock remains held until the reconciliation service commits
    or rolls back. SKIP LOCKED allows another worker to claim a
    different mapping concurrently.
    """

    stmt = (
        select(PortMapping)
        .where(
            PortMapping.status.in_(
                (
                    "pending",
                    "failed",
                    "releasing",
                )
            ),
            PortMapping.reconcile_action.in_(
                (
                    "apply",
                    "remove",
                )
            ),
        )
        .order_by(
            PortMapping.allocated_at,
            PortMapping.created_at,
            PortMapping.id,
        )
        .with_for_update(skip_locked=True)
        .limit(1)
    )

    return db.scalar(stmt)


def reconcile_gateway_batch(
    db: Session,
    *,
    limit: int = 100,
) -> GatewayReconciliationBatchResult:
    """
    Reconcile up to ``limit`` mappings, claiming one row at a time.

    Each mapping is locked independently so a commit performed by the
    reconciliation service cannot prematurely release locks belonging
    to later mappings in this batch.
    """

    if limit < 1:
        raise ValueError("limit must be at least 1.")

    if not settings.MIKROTIK_LIVE_ENABLED:
        raise GatewayOrchestrationError(
            "MikroTik live reconciliation is disabled."
        )

    succeeded = 0
    failed = 0
    mapping_ids: list[UUID] = []

    for _ in range(limit):
        mapping = claim_next_reconciliation_candidate(db)

        if mapping is None:
            break

        mapping_ids.append(mapping.id)

        try:
            reconcile_port_mapping_now(
                db,
                mapping=mapping,
                actor_user_id=None,
            )
        except GatewayOrchestrationError:
            failed += 1
            continue

        succeeded += 1

    return GatewayReconciliationBatchResult(
        selected=len(mapping_ids),
        succeeded=succeeded,
        failed=failed,
        mapping_ids=tuple(mapping_ids),
    )
