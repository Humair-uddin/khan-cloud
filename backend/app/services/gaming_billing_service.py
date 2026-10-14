from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from math import ceil
from uuid import UUID, uuid4

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.commercial import HostCapacityOffer, ProductSKU, RegionalRate
from app.models.compute import GamingSession
from app.models.finance import CustomerWallet, UsageReservation
from app.models.gaming_catalog import GamingTitle
from app.models.node import Node
from app.services.billing_policy import (
    METERED_MINIMUM_START_MINUTES,
    PRICE_BOOK_VERSION,
    SUPPORTED_SETTLEMENT_CURRENCIES,
)
from app.services.commercial_service import minute_rate_from_hourly
from app.services.settlement_service import (
    SettlementError,
    consume_reserved_platform_usage,
    consume_reserved_usage,
)
from app.services.wallet_service import (
    WalletError,
    extend_reservation,
    release_reservation,
    reserve_funds,
    wallet_balances,
)


class GamingBillingError(ValueError):
    pass


@dataclass(frozen=True)
class GamingCommercialAdmission:
    sku: ProductSKU
    wallet: CustomerWallet
    rate: RegionalRate
    currency: str
    region_code: str
    hourly_price_minor: int
    per_minute_price_minor: int
    admission_reserved_minor: int
    pricing_snapshot: dict[str, object]


def _region_for_currency(currency: str) -> str:
    for region, configured_currency in SUPPORTED_SETTLEMENT_CURRENCIES.items():
        if configured_currency == currency:
            return region
    raise GamingBillingError(f"No billing region is configured for {currency}.")


def _active_wallet_for_org(db: Session, organization_id: UUID) -> CustomerWallet:
    wallets = list(
        db.scalars(
            select(CustomerWallet)
            .where(
                CustomerWallet.organization_id == organization_id,
                CustomerWallet.status == "active",
            )
            .with_for_update()
        ).all()
    )
    if not wallets:
        raise GamingBillingError("A funded Khan Cloud wallet is required before Play.")
    if len(wallets) == 1:
        return wallets[0]

    funded = [w for w in wallets if wallet_balances(db, w)["available_minor"] > 0]
    if len(funded) == 1:
        return funded[0]
    raise GamingBillingError(
        "Customer billing currency is ambiguous; exactly one active funded wallet must apply to Play."
    )


def resolve_gaming_commercial_admission(
    db: Session,
    *,
    title: GamingTitle,
    organization_id: UUID,
) -> GamingCommercialAdmission:
    metadata = title.metadata_json if isinstance(title.metadata_json, dict) else {}
    sku_code = str(metadata.get("sku_code") or "").strip()
    if not sku_code:
        raise GamingBillingError(
            f"Gaming title {title.slug} has no server-controlled commercial SKU mapping."
        )

    sku = db.scalar(
        select(ProductSKU).where(
            ProductSKU.code == sku_code,
            ProductSKU.is_active.is_(True),
            ProductSKU.is_sellable.is_(True),
            ProductSKU.billing_mode == "metered",
        )
    )
    if sku is None:
        raise GamingBillingError(f"Gaming SKU {sku_code} is unavailable for sale.")

    wallet = _active_wallet_for_org(db, organization_id)
    region_code = _region_for_currency(wallet.currency)
    rate = db.scalar(
        select(RegionalRate).where(
            RegionalRate.sku_id == sku.id,
            RegionalRate.region_code == region_code,
            RegionalRate.currency == wallet.currency,
            RegionalRate.billing_period == "hourly",
            RegionalRate.metering_unit == "minute",
            RegionalRate.is_active.is_(True),
        )
    )
    if rate is None:
        raise GamingBillingError(
            f"No active {region_code}/{wallet.currency} hourly gaming rate exists for {sku.code}."
        )

    hourly = int(rate.unit_price_minor)
    per_minute = minute_rate_from_hourly(hourly)
    admission = per_minute * int(METERED_MINIMUM_START_MINUTES)
    balances = wallet_balances(db, wallet)
    if balances["available_minor"] < admission:
        raise GamingBillingError(
            "Insufficient available wallet balance for the minimum gaming admission window."
        )

    snapshot = {
        "price_book_version": PRICE_BOOK_VERSION,
        "sku_code": sku.code,
        "sku_name": sku.name,
        "game_slug": title.slug,
        "region_code": region_code,
        "currency": wallet.currency,
        "billing_period": rate.billing_period,
        "metering_unit": rate.metering_unit,
        "hourly_price_minor": hourly,
        "per_minute_price_minor": per_minute,
        "minimum_start_minutes": int(METERED_MINIMUM_START_MINUTES),
        "rate_id": str(rate.id),
    }
    return GamingCommercialAdmission(
        sku=sku,
        wallet=wallet,
        rate=rate,
        currency=wallet.currency,
        region_code=region_code,
        hourly_price_minor=hourly,
        per_minute_price_minor=per_minute,
        admission_reserved_minor=admission,
        pricing_snapshot=snapshot,
    )


def reserve_gaming_admission(
    db: Session,
    *,
    session: GamingSession,
    admission: GamingCommercialAdmission,
) -> UsageReservation:
    try:
        reservation = reserve_funds(
            db,
            wallet=admission.wallet,
            amount_minor=admission.admission_reserved_minor,
            idempotency_key=f"gaming:{session.id}:admission:v1",
            reference_type="gaming_session",
            reference_id=str(session.id),
        )
    except WalletError as exc:
        raise GamingBillingError(str(exc)) from exc

    session.product_sku_id = admission.sku.id
    session.usage_reservation_id = reservation.id
    session.billing_currency = admission.currency
    session.per_minute_price_minor = admission.per_minute_price_minor
    session.admission_reserved_minor = admission.admission_reserved_minor
    session.pricing_snapshot = dict(admission.pricing_snapshot)
    return reservation


def bind_gaming_host_economics(db: Session, *, session: GamingSession, node: Node, ownership_type: str) -> None:
    if session.product_sku_id is None:
        return
    if ownership_type == "khan_cloud":
        session.host_payout_per_minute_minor = 0
        return

    offer = db.scalar(
        select(HostCapacityOffer).where(
            HostCapacityOffer.node_id == node.id,
            HostCapacityOffer.sku_id == session.product_sku_id,
            HostCapacityOffer.currency == session.billing_currency,
            HostCapacityOffer.availability_state == "available",
            HostCapacityOffer.is_verified.is_(True),
        )
    )
    if offer is None:
        raise GamingBillingError(
            "Selected marketplace gaming host has no verified commercial capacity offer for this SKU."
        )
    host_per_minute = (
        minute_rate_from_hourly(int(offer.khan_cloud_payout_per_hour_minor))
        if int(offer.khan_cloud_payout_per_hour_minor) > 0
        else 0
    )
    if host_per_minute > session.per_minute_price_minor:
        raise GamingBillingError("Marketplace host payout exceeds the customer gaming rate.")
    session.host_payout_per_minute_minor = host_per_minute
    snapshot = dict(session.pricing_snapshot or {})
    snapshot.update({
        "provider_type": offer.provider_type,
        "host_capacity_offer_id": str(offer.id),
        "host_payout_per_minute_minor": host_per_minute,
    })
    session.pricing_snapshot = snapshot


def _reservation_for_update(db: Session, session: GamingSession) -> UsageReservation | None:
    if session.usage_reservation_id is None:
        return None
    return db.scalar(
        select(UsageReservation)
        .where(UsageReservation.id == session.usage_reservation_id)
        .with_for_update()
    )


def _remaining(reservation: UsageReservation) -> int:
    return reservation.reserved_minor - reservation.consumed_minor - reservation.released_minor


def _gaming_reservation_extension_idempotency_key(
    *,
    session_id: UUID,
    reservation_id: UUID,
    target_reserved_minor: int,
) -> str:
    """Bind an extension retry to one reservation lifecycle.

    Historical v1 keys omitted ``reservation_id`` and could therefore replay
    an extension transaction from an older reservation for the same gaming
    session. The v2 namespace is deliberately forward-only: a committed v1
    extension has already advanced ``reserved_minor``, while a collided v1
    no-op can be retried safely under the reservation-specific v2 key.
    """

    return (
        f"gaming:{session_id}:reservation:{reservation_id}:"
        f"extend:{target_reserved_minor}:v2"
    )


def ensure_runtime_coverage(db: Session, *, session: GamingSession) -> UsageReservation | None:
    reservation = _reservation_for_update(db, session)
    if reservation is None or reservation.status == "closed":
        return reservation
    required = session.per_minute_price_minor * int(METERED_MINIMUM_START_MINUTES)
    remaining = _remaining(reservation)
    if remaining >= required:
        return reservation
    wallet = db.scalar(
        select(CustomerWallet).where(CustomerWallet.id == reservation.wallet_id).with_for_update()
    )
    if wallet is None:
        raise GamingBillingError("Gaming wallet no longer exists.")
    topup = required - remaining
    if wallet_balances(db, wallet)["available_minor"] < topup:
        session.desired_state = "stopped"
        session.billing_stop_reason = "insufficient_wallet_balance"
        return reservation
    try:
        target_reserved_minor = reservation.reserved_minor + topup
        extend_reservation(
            db,
            reservation=reservation,
            amount_minor=topup,
            idempotency_key=_gaming_reservation_extension_idempotency_key(
                session_id=session.id,
                reservation_id=reservation.id,
                target_reserved_minor=target_reserved_minor,
            ),
        )
    except WalletError as exc:
        raise GamingBillingError(str(exc)) from exc
    return reservation



def _lock_gaming_session_for_billing(
    db: Session,
    session: GamingSession,
) -> GamingSession:
    """Serialize billing updates and track lock ownership across savepoints."""
    from sqlalchemy import inspect as sa_inspect

    if not isinstance(session, GamingSession):
        return session

    state = sa_inspect(session)
    if not state.persistent or state.session is not db:
        raise GamingBillingError(
            "Billing requires a persistent gaming session in this transaction."
        )

    transaction = db.get_transaction()
    if transaction is None:
        raise GamingBillingError(
            "Billing requires an active database transaction."
        )

    marker = db.info.get("_gaming_billing_lock_marker")

    if marker is None or marker[0] is not transaction:
        locked_ids = {}
        db.info["_gaming_billing_lock_marker"] = (
            transaction,
            locked_ids,
        )
    else:
        locked_ids = marker[1]

    nested = db.get_nested_transaction()
    current_owner = nested if nested is not None else transaction
    recorded_owner = locked_ids.get(session.id)

    if recorded_owner is not None:
        owner_is_active = recorded_owner.is_active
        owner_is_root = recorded_owner is transaction

        if owner_is_active and (
            owner_is_root or recorded_owner is current_owner
        ):
            db.flush([session])
            return session

    protected = {
        "usage_reservation_id",
        "billing_currency",
        "per_minute_price_minor",
        "host_payout_per_minute_minor",
        "admission_reserved_minor",
        "last_metered_at",
        "availability_cutoff_at",
        "availability_interrupted_at",
        "billing_finalized_at",
        "billing_stop_reason",
    }

    pending_lifecycle = {}

    for attr in state.mapper.column_attrs:
        key = attr.key
        history = state.attrs[key].history

        if history.has_changes() and key not in protected:
            pending_lifecycle[key] = getattr(session, key)

    with db.no_autoflush:
        locked = db.scalar(
            select(GamingSession)
            .where(GamingSession.id == session.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    if locked is None:
        raise GamingBillingError(
            "Gaming session disappeared during billing."
        )

    for key, value in pending_lifecycle.items():
        setattr(locked, key, value)

    locked_ids[session.id] = current_owner

    return locked


def meter_gaming_session(
    db: Session,
    *,
    session: GamingSession,
    now: datetime | None = None,
    force: bool = False,
) -> int:
    from datetime import timedelta

    from app.services.gaming_availability_policy import (
        availability_boundary,
        capped_time,
        utc,
    )

    session = _lock_gaming_session_for_billing(db, session)

    if getattr(session, "billing_finalized_at", None) is not None:
        return 0

    if session.product_sku_id is None or session.usage_reservation_id is None:
        return 0

    if (session.status != "running" and not force) or session.started_at is None:
        return 0

    requested_now = utc(now or datetime.now(UTC))

    node = db.get(Node, session.node_id) if session.node_id else None
    guest_node_id = getattr(session, "guest_node_id", None)
    guest_node = db.get(Node, guest_node_id) if guest_node_id else None

    required_nodes = [node]
    if guest_node_id is not None:
        required_nodes.append(guest_node)

    boundaries = [
        availability_boundary(n.last_seen_at) if n is not None else None
        for n in required_nodes
    ]

    heartbeat_boundary = (
        min(boundaries)
        if boundaries and all(boundary is not None for boundary in boundaries)
        else None
    )

    if heartbeat_boundary is None:
        anchor = session.last_metered_at or session.started_at

        if anchor is not None:
            anchor = utc(anchor)
            previous_cutoff = session.availability_cutoff_at

            if previous_cutoff is None or utc(previous_cutoff) > anchor:
                session.availability_cutoff_at = anchor

        session.availability_interrupted_at = requested_now
        session.failure_category = "host_heartbeat_unavailable"
        session.desired_state = "stopped"

        if node is not None:
            node.gaming_admission_auto_blocked = True

        return 0

    if requested_now > heartbeat_boundary:
        previous_cutoff = session.availability_cutoff_at

        if previous_cutoff is None or utc(previous_cutoff) > heartbeat_boundary:
            session.availability_cutoff_at = heartbeat_boundary
            session.availability_interrupted_at = requested_now
            session.failure_category = "host_heartbeat_stale"
            session.desired_state = "stopped"

            if node is not None:
                node.gaming_admission_auto_blocked = True

    current = capped_time(requested_now, session.availability_cutoff_at)

    anchor = session.last_metered_at or session.started_at
    anchor = utc(anchor)

    elapsed_seconds = max(0.0, (current - anchor).total_seconds())
    units = int(elapsed_seconds // 60)

    if units <= 0:
        if session.availability_cutoff_at is None:
            ensure_runtime_coverage(db, session=session)
        return 0

    reservation = (
        _reservation_for_update(db, session)
        if session.availability_cutoff_at is not None
        else ensure_runtime_coverage(db, session=session)
    )

    if reservation is None:
        return 0

    affordable_units = (
        _remaining(reservation)
        // max(1, session.per_minute_price_minor)
    )

    units = min(units, affordable_units)

    if units <= 0:
        session.desired_state = "stopped"
        session.billing_stop_reason = "reserved_funds_exhausted"
        return 0

    gross = units * session.per_minute_price_minor
    host_amount = units * session.host_payout_per_minute_minor

    period_end = anchor + timedelta(minutes=units)

    key = (
        f"gaming:{session.id}:reservation:{reservation.id}:usage:"
        f"{int(anchor.timestamp())}:{units}:v2"
    )

    try:
        if host_amount:
            consume_reserved_usage(
                db,
                reservation=reservation,
                host_node_id=session.node_id,
                gross_charge_minor=gross,
                host_amount_minor=host_amount,
                idempotency_key=key,
            )
        else:
            consume_reserved_platform_usage(
                db,
                reservation=reservation,
                gross_charge_minor=gross,
                idempotency_key=key,
            )
    except SettlementError as exc:
        raise GamingBillingError(str(exc)) from exc

    session.last_metered_at = period_end

    if session.availability_cutoff_at is None:
        ensure_runtime_coverage(db, session=session)

    return units



def finalize_gaming_billing(db: Session, *, session: GamingSession, reason: str) -> None:
    observed_reservation_id = getattr(session, "usage_reservation_id", None)
    session = _lock_gaming_session_for_billing(db, session)
    if (
        observed_reservation_id is not None
        and observed_reservation_id != session.usage_reservation_id
    ):
        raise GamingBillingError(
            "Stale finalization rejected: billing reservation changed."
        )
    if session.billing_finalized_at is not None:
        return
    now = datetime.now(UTC)
    if session.status in {"running", "stopping"} and session.started_at is not None:
        meter_gaming_session(db, session=session, now=now, force=True)
    reservation = _reservation_for_update(db, session)
    if reservation is not None:
        remaining = _remaining(reservation)
        if remaining > 0:
            try:
                release_reservation(
                    db,
                    reservation=reservation,
                    amount_minor=remaining,
                    idempotency_key=f"gaming:{session.id}:release:{reservation.id}:v1",
                )
            except WalletError as exc:
                raise GamingBillingError(str(exc)) from exc
    session.billing_finalized_at = now
    session.billing_stop_reason = reason[:80]


def reopen_gaming_billing(db: Session, *, session: GamingSession) -> None:
    observed_reservation_id = getattr(session, "usage_reservation_id", None)
    session = _lock_gaming_session_for_billing(db, session)
    if (
        observed_reservation_id is not None
        and observed_reservation_id != session.usage_reservation_id
    ):
        raise GamingBillingError(
            "Stale reopening rejected: billing reservation changed."
        )
    if session.product_sku_id is None:
        return
    if session.billing_finalized_at is None:
        ensure_runtime_coverage(db, session=session)
        return
    wallet = _active_wallet_for_org(db, session.organization_id)
    amount = session.per_minute_price_minor * int(METERED_MINIMUM_START_MINUTES)
    try:
        reservation = reserve_funds(
            db,
            wallet=wallet,
            amount_minor=amount,
            idempotency_key=f"gaming:{session.id}:restart:{uuid4()}:v1",
            reference_type="gaming_session_restart",
            reference_id=str(session.id),
        )
    except WalletError as exc:
        raise GamingBillingError(str(exc)) from exc
    session.usage_reservation_id = reservation.id
    session.admission_reserved_minor = amount
    session.last_metered_at = None
    session.availability_cutoff_at = None
    session.availability_interrupted_at = None
    session.billing_finalized_at = None
    session.billing_stop_reason = ""


def reconcile_gaming_billing_for_node(db: Session, *, node: Node) -> list[UUID]:
    sessions = list(
        db.scalars(
            select(GamingSession).where(
                GamingSession.status == "running",
                or_(GamingSession.node_id == node.id, GamingSession.guest_node_id == node.id),
            )
        ).all()
    )
    stop_ids: list[UUID] = []
    for session in sessions:
        try:
            meter_gaming_session(db, session=session)
        except GamingBillingError as exc:
            session.desired_state = "stopped"
            session.billing_stop_reason = "billing_reconciliation_failed"
            session.failure_category = "billing_reconciliation_failed"
            session.failure_message = str(exc)[:500]
        if session.desired_state == "stopped":
            stop_ids.append(session.id)
    return stop_ids
