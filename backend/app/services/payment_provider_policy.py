from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


class PaymentProviderPolicyError(ValueError):
    """Provider configuration cannot satisfy an attempted operation."""


@dataclass(frozen=True)
class ProviderOperationPolicy:
    capability: str | None = None
    currency: str | None = None
    presentment_currency: str | None = None
    settlement_currency: str | None = None
    allow_explicit_fx: bool = False


def _normalized_currency(value: str | None) -> str | None:
    if value is None:
        return None

    normalized = str(value).strip().upper()

    if not normalized:
        return None

    if len(normalized) != 3 or not normalized.isalpha():
        raise PaymentProviderPolicyError(
            f"Invalid ISO-style currency code: {value!r}"
        )

    return normalized


def _provider_capabilities(provider: Any) -> set[str]:
    raw = getattr(provider, "capabilities_json", None)

    if raw is None:
        raw = getattr(provider, "capabilities", None)

    if raw is None:
        return set()

    if isinstance(raw, dict):
        return {
            str(name).strip()
            for name, enabled in raw.items()
            if enabled and str(name).strip()
        }

    if isinstance(raw, (list, tuple, set, frozenset)):
        return {
            str(name).strip()
            for name in raw
            if str(name).strip()
        }

    raise PaymentProviderPolicyError(
        "Provider capabilities must be a mapping or collection."
    )


def _supported_currencies(provider: Any) -> set[str]:
    raw: Iterable[Any] | None = getattr(
        provider,
        "supported_currencies_json",
        None,
    )

    if raw is None:
        raw = getattr(
            provider,
            "supported_currencies",
            None,
        )

    if not raw:
        return set()

    result: set[str] = set()

    for value in raw:
        currency = _normalized_currency(str(value))

        if currency:
            result.add(currency)

    return result


def require_provider_enabled(provider: Any) -> None:
    enabled = getattr(provider, "enabled", None)

    if enabled is None:
        enabled = getattr(provider, "is_enabled", True)

    if not enabled:
        raise PaymentProviderPolicyError(
            "Payment provider is operationally disabled."
        )


def require_capability(
    provider: Any,
    capability: str,
) -> None:
    capability = str(capability or "").strip()

    if not capability:
        raise PaymentProviderPolicyError(
            "Capability is required."
        )

    available = _provider_capabilities(provider)

    if capability not in available:
        raise PaymentProviderPolicyError(
            f"Provider does not support capability {capability!r}."
        )


def require_supported_currency(
    provider: Any,
    currency: str,
) -> str:
    normalized = _normalized_currency(currency)

    if normalized is None:
        raise PaymentProviderPolicyError(
            "Currency is required."
        )

    supported = _supported_currencies(provider)

    if supported and normalized not in supported:
        raise PaymentProviderPolicyError(
            f"Provider does not support currency {normalized}."
        )

    return normalized


def validate_currency_semantics(
    *,
    transaction_currency: str,
    presentment_currency: str | None = None,
    settlement_currency: str | None = None,
    allow_explicit_fx: bool = False,
) -> tuple[str, str, str]:
    transaction = _normalized_currency(
        transaction_currency
    )

    if transaction is None:
        raise PaymentProviderPolicyError(
            "Transaction currency is required."
        )

    presentment = (
        _normalized_currency(presentment_currency)
        or transaction
    )

    settlement = (
        _normalized_currency(settlement_currency)
        or presentment
    )

    if transaction != presentment:
        raise PaymentProviderPolicyError(
            "Transaction currency must equal presentment currency; "
            "implicit customer-side FX is forbidden."
        )

    if settlement != presentment and not allow_explicit_fx:
        raise PaymentProviderPolicyError(
            "Presentment and settlement currencies differ but "
            "no explicit auditable FX transaction was supplied."
        )

    return transaction, presentment, settlement


def enforce_provider_operation(
    provider: Any,
    policy: ProviderOperationPolicy,
) -> tuple[str | None, str | None, str | None]:
    require_provider_enabled(provider)

    if policy.capability:
        require_capability(
            provider,
            policy.capability,
        )

    transaction_currency = None

    if policy.currency:
        transaction_currency = require_supported_currency(
            provider,
            policy.currency,
        )

    if (
        transaction_currency
        or policy.presentment_currency
        or policy.settlement_currency
    ):
        if transaction_currency is None:
            transaction_currency = (
                _normalized_currency(
                    policy.presentment_currency
                )
                or _normalized_currency(
                    policy.settlement_currency
                )
            )

        assert transaction_currency is not None

        transaction, presentment, settlement = (
            validate_currency_semantics(
                transaction_currency=transaction_currency,
                presentment_currency=(
                    policy.presentment_currency
                ),
                settlement_currency=(
                    policy.settlement_currency
                ),
                allow_explicit_fx=(
                    policy.allow_explicit_fx
                ),
            )
        )

        require_supported_currency(
            provider,
            presentment,
        )

        require_supported_currency(
            provider,
            settlement,
        )

        return transaction, presentment, settlement

    return None, None, None
