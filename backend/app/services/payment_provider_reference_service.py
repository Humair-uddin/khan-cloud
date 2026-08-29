from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.payment_provider import (
    PaymentProvider,
    PaymentProviderReference,
)


class PaymentProviderReferenceError(ValueError):
    pass


def bind_provider_reference(
    db: Session,
    *,
    provider: PaymentProvider,
    reference_type: str,
    provider_reference: str,
    internal_resource_type: str,
    internal_resource_id: UUID,
    metadata_json: dict | None = None,
) -> PaymentProviderReference:
    reference_type = reference_type.strip()
    provider_reference = provider_reference.strip()
    internal_resource_type = internal_resource_type.strip()

    if not reference_type:
        raise PaymentProviderReferenceError(
            "Provider reference type is required."
        )

    if not provider_reference:
        raise PaymentProviderReferenceError(
            "Provider external reference is required."
        )

    if not internal_resource_type:
        raise PaymentProviderReferenceError(
            "Internal resource type is required."
        )

    existing = db.scalar(
        select(PaymentProviderReference).where(
            PaymentProviderReference.provider_id == provider.id,
            PaymentProviderReference.reference_type == reference_type,
            PaymentProviderReference.provider_reference
            == provider_reference,
        )
    )

    if existing is not None:
        if (
            existing.internal_resource_type
            != internal_resource_type
            or existing.internal_resource_id
            != internal_resource_id
        ):
            raise PaymentProviderReferenceError(
                "Provider external reference is already bound "
                "to a different internal resource."
            )

        existing_metadata = dict(
            existing.metadata_json or {}
        )
        supplied_metadata = dict(
            metadata_json or {}
        )

        for key, value in supplied_metadata.items():
            current = existing_metadata.get(key)

            if current is not None and current != value:
                raise PaymentProviderReferenceError(
                    "Provider reference metadata was replayed "
                    "with conflicting contents."
                )

        if supplied_metadata:
            existing_metadata.update(supplied_metadata)
            existing.metadata_json = existing_metadata
            db.flush()

        return existing

    reference = PaymentProviderReference(
        provider_id=provider.id,
        reference_type=reference_type,
        provider_reference=provider_reference,
        internal_resource_type=internal_resource_type,
        internal_resource_id=internal_resource_id,
        metadata_json=dict(metadata_json or {}),
    )

    db.add(reference)
    db.flush()

    return reference
