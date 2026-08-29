from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from typing import Any, Callable, Protocol


class PaymentAdapterError(RuntimeError):
    pass


class PaymentAdapter(Protocol):
    adapter_type: str

    def healthcheck(self) -> dict[str, Any]:
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

    #
    # Crucial architecture rule:
    #
    # provider.code identifies a merchant/provider ACCOUNT INSTANCE.
    # provider.adapter_type identifies reusable implementation code.
    #
    return registration.factory(
        provider=provider,
        **kwargs,
    )


def clear_adapter_registry_for_tests() -> None:
    with _lock:
        _registry.clear()
