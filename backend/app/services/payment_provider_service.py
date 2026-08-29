from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.payment_provider import PaymentProvider


class PaymentProviderError(ValueError):
    pass


def create_provider(
    db: Session,
    *,
    code: str,
    display_name: str,
    adapter_type: str,
    environment: str,
    enabled: bool,
    capabilities: dict,
    supported_currencies: list[str],
    credential_reference: str = "",
    webhook_secret_reference: str = "",
    webhook_tolerance_seconds: int = 300,
) -> PaymentProvider:
    code = code.strip().lower()

    if not code:
        raise PaymentProviderError(
            "Provider code is required."
        )

    if environment not in {"sandbox", "production"}:
        raise PaymentProviderError(
            "Provider environment is invalid."
        )

    existing = db.scalar(
        select(PaymentProvider).where(
            PaymentProvider.code == code
        )
    )

    if existing is not None:
        raise PaymentProviderError(
            "Payment provider already exists."
        )

    currencies = sorted(
        {
            currency.strip().upper()
            for currency in supported_currencies
            if currency.strip()
        }
    )

    if any(len(currency) != 3 for currency in currencies):
        raise PaymentProviderError(
            "Provider currencies must be ISO-style 3-character codes."
        )

    provider = PaymentProvider(
        code=code,
        display_name=display_name.strip(),
        adapter_type=adapter_type.strip(),
        environment=environment,
        enabled=enabled,
        capabilities_json=dict(capabilities),
        supported_currencies_json=currencies,
        credential_reference=credential_reference.strip(),
        webhook_secret_reference=webhook_secret_reference.strip(),
        webhook_tolerance_seconds=webhook_tolerance_seconds,
        status="active" if enabled else "configured",
    )

    db.add(provider)
    db.flush()

    return provider


def get_provider(
    db: Session,
    *,
    code: str,
    require_enabled: bool = False,
) -> PaymentProvider:
    provider = db.scalar(
        select(PaymentProvider).where(
            PaymentProvider.code == code.strip().lower()
        )
    )

    if provider is None:
        raise PaymentProviderError(
            "Payment provider is not configured."
        )

    if require_enabled and not provider.enabled:
        raise PaymentProviderError(
            "Payment provider is disabled."
        )

    return provider
