from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from threading import RLock
from typing import Any, Callable, Protocol


class PaymentAdapterError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProviderSettlementItemResult:
    provider_line_id: str
    provider_transaction_reference: str
    event_type: str
    presentment_currency: str
    settlement_currency: str
    gross_amount_minor: int
    fee_amount_minor: int
    net_amount_minor: int
    occurred_at: datetime | None = None
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class ProviderSettlementBatchResult:
    provider_settlement_reference: str
    settlement_currency: str
    settlement_date: datetime | None
    items: tuple[ProviderSettlementItemResult, ...]
    metadata: dict[str, Any] | None = None


class PaymentAdapter(Protocol):
    adapter_type: str

    def healthcheck(self) -> dict[str, Any]:
        ...

    def capture_payment(
        self,
        *,
        amount_minor: int,
        currency: str,
        idempotency_key: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ...

    def execute_refund(
        self,
        *,
        refund_id: str,
        amount_minor: int,
        currency: str,
        provider_reference: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        ...

    def execute_payout(
        self,
        *,
        payout_id: str,
        amount_minor: int,
        currency: str,
        payout_method: dict[str, Any],
        idempotency_key: str,
    ) -> dict[str, Any]:
        ...

    def fetch_settlement_batches(
        self,
        *,
        cursor: str | None = None,
    ) -> list[ProviderSettlementBatchResult] | list[dict[str, Any]]:
        ...

    def lookup_transaction(
        self,
        *,
        provider_reference: str,
    ) -> dict[str, Any]:
        ...

    def get_balance(self) -> dict[str, Any]:
        ...


AdapterFactory = Callable[..., PaymentAdapter]


@dataclass(frozen=True)
class RegisteredPaymentAdapter:
    adapter_type: str
    factory: AdapterFactory


_registry: dict[str, RegisteredPaymentAdapter] = {}
_lock = RLock()


def normalize_adapter_type(value: str) -> str:
    normalized = str(value or "").strip().lower()

    if not normalized:
        raise PaymentAdapterError(
            "adapter_type is required."
        )

    if not all(
        ch.isalnum() or ch in {"_", "-", "."}
        for ch in normalized
    ):
        raise PaymentAdapterError(
            "adapter_type contains unsupported characters."
        )

    return normalized


def register_adapter(
    adapter_type: str,
    factory: AdapterFactory,
    *,
    replace: bool = False,
) -> None:
    normalized = normalize_adapter_type(
        adapter_type
    )

    if not callable(factory):
        raise PaymentAdapterError(
            "Adapter factory must be callable."
        )

    with _lock:
        if normalized in _registry and not replace:
            raise PaymentAdapterError(
                f"Adapter type {normalized!r} is already registered."
            )

        _registry[normalized] = RegisteredPaymentAdapter(
            adapter_type=normalized,
            factory=factory,
        )


def registered_adapter_types() -> tuple[str, ...]:
    with _lock:
        return tuple(sorted(_registry))


def create_adapter_for_provider(
    provider: Any,
    **kwargs: Any,
) -> PaymentAdapter:
    adapter_type = normalize_adapter_type(
        getattr(provider, "adapter_type", "")
    )

    with _lock:
        registration = _registry.get(
            adapter_type
        )

    if registration is None:
        raise PaymentAdapterError(
            f"No adapter implementation is registered for "
            f"adapter_type={adapter_type!r}."
        )

    # provider.code is an account instance.
    # provider.adapter_type is reusable implementation code.
    return registration.factory(
        provider=provider,
        **kwargs,
    )


def clear_adapter_registry_for_tests() -> None:
    with _lock:
        _registry.clear()
