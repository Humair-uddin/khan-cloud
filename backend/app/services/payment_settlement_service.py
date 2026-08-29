from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.payment_provider import PaymentProvider
from app.models.payment_settlement import (
    PaymentProviderSettlementBatch,
    PaymentProviderSettlementItem,
)
from app.services.payment_adapter_registry import (
    ProviderSettlementBatchResult,
    ProviderSettlementItemResult,
)
from app.services.payment_provider_policy import (
    ProviderOperationPolicy,
    enforce_provider_operation,
)


class PaymentSettlementError(ValueError):
    pass


def canonical_settlement_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")

    return hashlib.sha256(encoded).hexdigest()


def _normalize_currency(value: str) -> str:
    currency = str(value or "").strip().upper()

    if (
        len(currency) != 3
        or not currency.isalpha()
    ):
        raise PaymentSettlementError(
            "Settlement currency must be a 3-character code."
        )

    return currency


def _normalize_item(
    item: ProviderSettlementItemResult | dict[str, Any],
) -> dict[str, Any]:
    if isinstance(item, ProviderSettlementItemResult):
        value = {
            "provider_line_id": item.provider_line_id,
            "provider_transaction_reference": (
                item.provider_transaction_reference
            ),
            "event_type": item.event_type,
            "presentment_currency": item.presentment_currency,
            "settlement_currency": item.settlement_currency,
            "gross_amount_minor": item.gross_amount_minor,
            "fee_amount_minor": item.fee_amount_minor,
            "net_amount_minor": item.net_amount_minor,
            "metadata": dict(item.metadata or {}),
        }
    elif isinstance(item, dict):
        value = dict(item)
    else:
        raise PaymentSettlementError(
            "Settlement item must be a normalized record or mapping."
        )

    provider_line_id = str(
        value.get("provider_line_id") or ""
    ).strip()

    provider_reference = str(
        value.get("provider_transaction_reference") or ""
    ).strip()

    event_type = str(
        value.get("event_type") or ""
    ).strip().lower()

    if not provider_line_id:
        raise PaymentSettlementError(
            "Provider settlement line ID is required."
        )

    if not provider_reference:
        raise PaymentSettlementError(
            "Provider transaction reference is required."
        )

    if not event_type:
        raise PaymentSettlementError(
            "Provider settlement event type is required."
        )

    presentment = _normalize_currency(
        value.get("presentment_currency")
    )

    settlement = _normalize_currency(
        value.get("settlement_currency")
    )

    gross = int(
        value.get("gross_amount_minor", -1)
    )
    fee = int(
        value.get("fee_amount_minor", -1)
    )
    net = int(
        value.get("net_amount_minor", -1)
    )

    if gross < 0 or fee < 0 or net < 0:
        raise PaymentSettlementError(
            "Settlement amounts cannot be negative."
        )

    if net != gross - fee:
        raise PaymentSettlementError(
            "Settlement net must equal gross minus fee."
        )

    explicit_fx_transaction_id = value.get(
        "explicit_fx_transaction_id"
    )

    if presentment != settlement:
        if not explicit_fx_transaction_id:
            raise PaymentSettlementError(
                "Presentment and settlement currencies differ; "
                "an explicit auditable FX transaction is required."
            )

        explicit_fx_transaction_id = UUID(
            str(explicit_fx_transaction_id)
        )

    normalized = {
        "provider_line_id": provider_line_id,
        "provider_transaction_reference": provider_reference,
        "event_type": event_type,
        "presentment_currency": presentment,
        "settlement_currency": settlement,
        "gross_amount_minor": gross,
        "fee_amount_minor": fee,
        "net_amount_minor": net,
        "explicit_fx_transaction_id": (
            str(explicit_fx_transaction_id)
            if explicit_fx_transaction_id
            else None
        ),
        "metadata": dict(
            value.get("metadata") or {}
        ),
    }

    return normalized


def ingest_provider_settlement(
    db: Session,
    *,
    provider: PaymentProvider,
    provider_settlement_reference: str,
    settlement_currency: str,
    settlement_date: datetime | None,
    items: list[
        ProviderSettlementItemResult | dict[str, Any]
    ],
    idempotency_key: str,
    credential_reference_snapshot: str = "",
    metadata_json: dict[str, Any] | None = None,
) -> tuple[PaymentProviderSettlementBatch, bool]:
    reference = str(
        provider_settlement_reference or ""
    ).strip()

    key = str(
        idempotency_key or ""
    ).strip()

    if not reference:
        raise PaymentSettlementError(
            "Provider settlement reference is required."
        )

    if not key:
        raise PaymentSettlementError(
            "Settlement idempotency key is required."
        )

    if not items:
        raise PaymentSettlementError(
            "Settlement batch must contain at least one item."
        )

    currency = _normalize_currency(
        settlement_currency
    )

    enforce_provider_operation(
        provider,
        ProviderOperationPolicy(
            capability="treasury_settlement",
            currency=currency,
            presentment_currency=currency,
            settlement_currency=currency,
            allow_explicit_fx=False,
        ),
    )

    normalized_items = [
        _normalize_item(item)
        for item in items
    ]

    line_ids = [
        item["provider_line_id"]
        for item in normalized_items
    ]

    if len(line_ids) != len(set(line_ids)):
        raise PaymentSettlementError(
            "Provider settlement contains duplicate line IDs."
        )

    for item in normalized_items:
        if item["settlement_currency"] != currency:
            raise PaymentSettlementError(
                "Settlement item currency does not match "
                "its settlement batch."
            )

    gross = sum(
        item["gross_amount_minor"]
        for item in normalized_items
    )
    fee = sum(
        item["fee_amount_minor"]
        for item in normalized_items
    )
    net = sum(
        item["net_amount_minor"]
        for item in normalized_items
    )

    canonical = {
        "provider_id": str(provider.id),
        "provider_code": provider.code,
        "provider_settlement_reference": reference,
        "settlement_currency": currency,
        "settlement_date": (
            settlement_date.isoformat()
            if settlement_date
            else None
        ),
        "gross_amount_minor": gross,
        "fee_amount_minor": fee,
        "net_amount_minor": net,
        "items": normalized_items,
    }

    content_hash = canonical_settlement_hash(
        canonical
    )

    existing = db.scalar(
        select(PaymentProviderSettlementBatch).where(
            PaymentProviderSettlementBatch.idempotency_key
            == key
        )
    )

    if existing is not None:
        if (
            existing.provider_id != provider.id
            or existing.provider_settlement_reference
            != reference
            or existing.content_hash != content_hash
        ):
            raise PaymentSettlementError(
                "Settlement idempotency key was reused with different contents."
            )

        return existing, True

    existing_reference = db.scalar(
        select(PaymentProviderSettlementBatch).where(
            PaymentProviderSettlementBatch.provider_id
            == provider.id,
            PaymentProviderSettlementBatch
            .provider_settlement_reference
            == reference,
        )
    )

    if existing_reference is not None:
        if (
            existing_reference.content_hash
            != content_hash
        ):
            raise PaymentSettlementError(
                "Provider settlement reference was replayed with different contents."
            )

        return existing_reference, True

    batch = PaymentProviderSettlementBatch(
        provider_id=provider.id,
        provider_code=provider.code,
        provider_settlement_reference=reference,
        settlement_currency=currency,
        gross_amount_minor=gross,
        fee_amount_minor=fee,
        net_amount_minor=net,
        settlement_date=settlement_date,
        status="received",
        content_hash=content_hash,
        idempotency_key=key,
        credential_reference_snapshot=(
            str(credential_reference_snapshot or "").strip()
        ),
        metadata_json=dict(
            metadata_json or {}
        ),
    )

    db.add(batch)
    db.flush()

    for item in normalized_items:
        item_hash = canonical_settlement_hash(
            item
        )

        row = PaymentProviderSettlementItem(
            settlement_batch_id=batch.id,
            provider_line_id=(
                item["provider_line_id"]
            ),
            provider_transaction_reference=(
                item["provider_transaction_reference"]
            ),
            event_type=item["event_type"],
            presentment_currency=(
                item["presentment_currency"]
            ),
            settlement_currency=(
                item["settlement_currency"]
            ),
            gross_amount_minor=(
                item["gross_amount_minor"]
            ),
            fee_amount_minor=(
                item["fee_amount_minor"]
            ),
            net_amount_minor=(
                item["net_amount_minor"]
            ),
            explicit_fx_transaction_id=(
                UUID(
                    item["explicit_fx_transaction_id"]
                )
                if item[
                    "explicit_fx_transaction_id"
                ]
                else None
            ),
            content_hash=item_hash,
            reconciliation_status="pending_review",
            metadata_json=dict(
                item["metadata"]
            ),
        )

        db.add(row)

    db.flush()

    return batch, False
