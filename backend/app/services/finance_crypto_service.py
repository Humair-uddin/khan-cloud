from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings


class FinanceCryptoError(RuntimeError):
    pass


def _load_key() -> tuple[str, bytes]:
    version = settings.FINANCE_ENCRYPTION_KEY_VERSION.strip()

    encoded = settings.FINANCE_ENCRYPTION_KEY_B64.strip()

    if not version or not encoded:
        raise FinanceCryptoError(
            "Finance encryption key is not configured."
        )

    try:
        key = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise FinanceCryptoError(
            "Finance encryption key is not valid base64."
        ) from exc

    if len(key) != 32:
        raise FinanceCryptoError(
            "Finance encryption key must be exactly 256 bits."
        )

    return version, key


def encrypt_financial_payload(
    payload: dict,
    *,
    aad: str,
) -> tuple[str, str]:
    version, key = _load_key()

    nonce = os.urandom(12)

    plaintext = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()

    ciphertext = AESGCM(key).encrypt(
        nonce,
        plaintext,
        aad.encode(),
    )

    envelope = base64.b64encode(
        nonce + ciphertext
    ).decode()

    return envelope, version


def decrypt_financial_payload(
    envelope: str,
    *,
    aad: str,
) -> dict:
    _, key = _load_key()

    raw = base64.b64decode(
        envelope,
        validate=True,
    )

    if len(raw) < 13:
        raise FinanceCryptoError(
            "Invalid encrypted finance envelope."
        )

    nonce = raw[:12]
    ciphertext = raw[12:]

    plaintext = AESGCM(key).decrypt(
        nonce,
        ciphertext,
        aad.encode(),
    )

    return json.loads(plaintext)


def financial_fingerprint(value: str) -> str:
    """
    Produce a deterministic searchable fingerprint without storing
    a plain SHA-256 digest of a bank account/IBAN/token identifier.

    The master finance encryption key is used as HMAC key material,
    with domain separation so encryption and fingerprint purposes
    remain logically distinct.
    """
    key = _load_key()

    normalized = str(value).strip().encode("utf-8")

    if not normalized:
        raise FinanceCryptoError(
            "Fingerprint source must not be blank."
        )

    message = (
        b"khan-cloud-finance-fingerprint-v1\x00"
        + normalized
    )

    return hmac.new(
        key,
        message,
        hashlib.sha256,
    ).hexdigest()
