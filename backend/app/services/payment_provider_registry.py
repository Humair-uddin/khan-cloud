from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.schemas.payment_provider import NormalizedPaymentEvent


class PaymentAdapterError(ValueError):
    pass


@dataclass(frozen=True)
class ProviderCapabilities:
    deposits: bool = False
    refunds: bool = False
    chargebacks: bool = False
    payouts: bool = False
    treasury_settlement: bool = False


class PaymentProviderAdapter(Protocol):
    code: str
    capabilities: ProviderCapabilities

    def verify_webhook(
        self,
        *,
        raw_body: bytes,
        headers: dict[str, str],
        secret: str,
    ) -> bool:
        ...

    def normalize_webhook(
        self,
        *,
        raw_body: bytes,
        headers: dict[str, str],
    ) -> NormalizedPaymentEvent:
        ...


_REGISTRY: dict[str, PaymentProviderAdapter] = {}


def register_adapter(
    adapter: PaymentProviderAdapter,
    *,
    replace: bool = False,
) -> None:
    code = adapter.code.strip().lower()

    if not code:
        raise PaymentAdapterError(
            "Payment adapter code is required."
        )

    if code in _REGISTRY and not replace:
        raise PaymentAdapterError(
            f"Payment adapter is already registered: {code}"
        )

    _REGISTRY[code] = adapter


def get_adapter(code: str) -> PaymentProviderAdapter:
    normalized = code.strip().lower()

    adapter = _REGISTRY.get(normalized)

    if adapter is None:
        raise PaymentAdapterError(
            f"No payment adapter registered for provider: {normalized}"
        )

    return adapter


def registered_adapter_codes() -> tuple[str, ...]:
    return tuple(sorted(_REGISTRY))


def clear_adapter_registry_for_tests() -> None:
    _REGISTRY.clear()
