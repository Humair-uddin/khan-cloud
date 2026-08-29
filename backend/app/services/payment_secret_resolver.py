from __future__ import annotations

import os
from dataclasses import dataclass
from threading import RLock
from typing import Callable


class PaymentSecretError(RuntimeError):
    pass


SecretResolver = Callable[[str], str]


@dataclass(frozen=True)
class SecretReference:
    scheme: str
    locator: str


_resolvers: dict[str, SecretResolver] = {}
_lock = RLock()


def parse_secret_reference(
    reference: str,
) -> SecretReference:
    value = str(reference or "").strip()

    if not value:
        raise PaymentSecretError(
            "Secret reference is required."
        )

    if ":" not in value:
        raise PaymentSecretError(
            "Secret references must be scheme-qualified."
        )

    scheme, locator = value.split(":", 1)

    scheme = scheme.strip().lower()
    locator = locator.strip()

    if not scheme or not locator:
        raise PaymentSecretError(
            "Secret reference requires scheme and locator."
        )

    if scheme in {
        "literal",
        "plaintext",
        "raw",
        "secret",
    }:
        raise PaymentSecretError(
            "Literal/plaintext payment secrets are forbidden."
        )

    return SecretReference(
        scheme=scheme,
        locator=locator,
    )


def register_secret_resolver(
    scheme: str,
    resolver: SecretResolver,
    *,
    replace: bool = False,
) -> None:
    normalized = str(scheme or "").strip().lower()

    if not normalized:
        raise PaymentSecretError(
            "Secret resolver scheme is required."
        )

    if not callable(resolver):
        raise PaymentSecretError(
            "Secret resolver must be callable."
        )

    with _lock:
        if normalized in _resolvers and not replace:
            raise PaymentSecretError(
                f"Secret resolver {normalized!r} already exists."
            )

        _resolvers[normalized] = resolver


def _resolve_env(locator: str) -> str:
    value = os.environ.get(locator)

    if value is None or value == "":
        raise PaymentSecretError(
            f"Environment secret {locator!r} is unavailable."
        )

    return value


def resolve_secret(reference: str) -> str:
    parsed = parse_secret_reference(
        reference
    )

    with _lock:
        resolver = _resolvers.get(
            parsed.scheme
        )

    if resolver is None:
        raise PaymentSecretError(
            f"No secret resolver is registered for "
            f"{parsed.scheme!r}."
        )

    value = resolver(parsed.locator)

    if not isinstance(value, str) or value == "":
        raise PaymentSecretError(
            "Secret resolver returned an empty/non-string value."
        )

    return value


def validate_secret_reference(
    reference: str,
) -> SecretReference:
    parsed = parse_secret_reference(
        reference
    )

    with _lock:
        if parsed.scheme not in _resolvers:
            raise PaymentSecretError(
                f"Unknown secret-reference scheme "
                f"{parsed.scheme!r}."
            )

    return parsed


#
# Environment remains supported, but callers now depend on an
# abstraction capable of KMS/Vault/HSM resolvers without changing
# financial/provider domain code.
#
register_secret_resolver(
    "env",
    _resolve_env,
)
