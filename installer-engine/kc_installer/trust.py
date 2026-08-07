from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PublicKey,
)


SIGNATURE_FILENAME = "signature.json"


@dataclass(frozen=True)
class PackageTrustResult:
    trusted: bool
    signer_id: str | None
    package_digest: str
    reason: str


def package_digest(package_dir: Path) -> str:
    """
    Produce a deterministic SHA-256 digest of the package contents.

    signature.json is excluded because it contains the signature over
    this digest.
    """

    package_dir = package_dir.resolve()

    if not package_dir.is_dir():
        raise ValueError(
            f"Package directory does not exist: {package_dir}"
        )

    digest = hashlib.sha256()

    files = sorted(
        (
            path
            for path in package_dir.rglob("*")
            if path.is_file()
            and path.name != SIGNATURE_FILENAME
        ),
        key=lambda path: path.relative_to(package_dir).as_posix(),
    )

    for path in files:
        relative = path.relative_to(package_dir).as_posix().encode()

        digest.update(relative)
        digest.update(b"\0")

        with path.open("rb") as handle:
            for chunk in iter(
                lambda: handle.read(1024 * 1024),
                b"",
            ):
                digest.update(chunk)

        digest.update(b"\0")

    return digest.hexdigest()


def load_trusted_keys(
    trust_store: Path,
) -> dict[str, Ed25519PublicKey]:
    """
    Load trusted Ed25519 public keys from JSON files.

    Each file must contain:
      {
        "signer_id": "...",
        "public_key": "<base64 raw 32-byte Ed25519 public key>"
      }
    """

    trusted: dict[str, Ed25519PublicKey] = {}

    if not trust_store.exists():
        return trusted

    if not trust_store.is_dir():
        raise ValueError(
            f"Trust store is not a directory: {trust_store}"
        )

    for path in sorted(trust_store.glob("*.json")):
        raw = json.loads(path.read_text())

        signer_id = raw.get("signer_id")
        encoded_key = raw.get("public_key")

        if not isinstance(signer_id, str) or not signer_id:
            raise ValueError(
                f"Invalid signer_id in trusted key file: {path}"
            )

        if not isinstance(encoded_key, str) or not encoded_key:
            raise ValueError(
                f"Invalid public_key in trusted key file: {path}"
            )

        if signer_id in trusted:
            raise ValueError(
                f"Duplicate trusted signer_id: {signer_id}"
            )

        try:
            key_bytes = base64.b64decode(
                encoded_key,
                validate=True,
            )
        except Exception as exc:
            raise ValueError(
                f"Invalid base64 public key in {path}"
            ) from exc

        if len(key_bytes) != 32:
            raise ValueError(
                f"Invalid Ed25519 public key length in {path}"
            )

        trusted[signer_id] = (
            Ed25519PublicKey.from_public_bytes(key_bytes)
        )

    return trusted


def verify_package_signature(
    package_dir: Path,
    trust_store: Path,
) -> PackageTrustResult:
    digest = package_digest(package_dir)
    signature_path = package_dir / SIGNATURE_FILENAME

    if not signature_path.exists():
        return PackageTrustResult(
            trusted=False,
            signer_id=None,
            package_digest=digest,
            reason="package signature is missing",
        )

    try:
        raw = json.loads(signature_path.read_text())
    except Exception:
        return PackageTrustResult(
            trusted=False,
            signer_id=None,
            package_digest=digest,
            reason="package signature metadata is invalid",
        )

    signer_id = raw.get("signer_id")
    encoded_signature = raw.get("signature")

    if not isinstance(signer_id, str) or not signer_id:
        return PackageTrustResult(
            trusted=False,
            signer_id=None,
            package_digest=digest,
            reason="package signer_id is missing or invalid",
        )

    if not isinstance(encoded_signature, str):
        return PackageTrustResult(
            trusted=False,
            signer_id=signer_id,
            package_digest=digest,
            reason="package signature is missing or invalid",
        )

    try:
        trusted_keys = load_trusted_keys(trust_store)
    except ValueError as exc:
        return PackageTrustResult(
            trusted=False,
            signer_id=signer_id,
            package_digest=digest,
            reason=f"trust store error: {exc}",
        )

    public_key = trusted_keys.get(signer_id)

    if public_key is None:
        return PackageTrustResult(
            trusted=False,
            signer_id=signer_id,
            package_digest=digest,
            reason="package signer is not trusted",
        )

    try:
        signature = base64.b64decode(
            encoded_signature,
            validate=True,
        )
    except Exception:
        return PackageTrustResult(
            trusted=False,
            signer_id=signer_id,
            package_digest=digest,
            reason="package signature encoding is invalid",
        )

    try:
        public_key.verify(
            signature,
            digest.encode("ascii"),
        )
    except InvalidSignature:
        return PackageTrustResult(
            trusted=False,
            signer_id=signer_id,
            package_digest=digest,
            reason="package signature verification failed",
        )

    return PackageTrustResult(
        trusted=True,
        signer_id=signer_id,
        package_digest=digest,
        reason="trusted signature verified",
    )
