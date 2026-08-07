import base64
import json
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)

from kc_installer.trust import (
    package_digest,
    verify_package_signature,
)


def create_package(tmp_path: Path) -> Path:
    package = tmp_path / "package"
    package.mkdir()

    (package / "manifest.yaml").write_text(
        """
feature_pack:
  id: FP-SIGNED
  name: Signed Test
  version: 1.0.0
  signed: true

components: {}
"""
    )

    payload = package / "payload"
    payload.mkdir()

    (payload / "example.txt").write_text(
        "original payload"
    )

    return package


def create_signer(
    tmp_path: Path,
    signer_id: str = "khan-cloud-test",
):
    private_key = Ed25519PrivateKey.generate()

    public_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )

    trust_store = tmp_path / "trust"
    trust_store.mkdir()

    (trust_store / f"{signer_id}.json").write_text(
        json.dumps(
            {
                "signer_id": signer_id,
                "public_key": base64.b64encode(
                    public_bytes
                ).decode(),
            }
        )
    )

    return private_key, trust_store


def sign_package(
    package: Path,
    private_key: Ed25519PrivateKey,
    *,
    signer_id: str = "khan-cloud-test",
) -> None:
    digest = package_digest(package)

    signature = private_key.sign(
        digest.encode("ascii")
    )

    (package / "signature.json").write_text(
        json.dumps(
            {
                "signer_id": signer_id,
                "algorithm": "ed25519",
                "signature": base64.b64encode(
                    signature
                ).decode(),
            }
        )
    )


def test_valid_signature_is_trusted(
    tmp_path: Path,
) -> None:
    package = create_package(tmp_path)

    private_key, trust_store = create_signer(tmp_path)

    sign_package(package, private_key)

    result = verify_package_signature(
        package,
        trust_store,
    )

    assert result.trusted is True
    assert result.signer_id == "khan-cloud-test"
    assert result.reason == "trusted signature verified"


def test_unsigned_package_is_not_trusted(
    tmp_path: Path,
) -> None:
    package = create_package(tmp_path)

    _, trust_store = create_signer(tmp_path)

    result = verify_package_signature(
        package,
        trust_store,
    )

    assert result.trusted is False
    assert result.reason == "package signature is missing"


def test_modified_manifest_breaks_signature(
    tmp_path: Path,
) -> None:
    package = create_package(tmp_path)

    private_key, trust_store = create_signer(tmp_path)

    sign_package(package, private_key)

    manifest = package / "manifest.yaml"

    manifest.write_text(
        manifest.read_text()
        + "\n# tampered\n"
    )

    result = verify_package_signature(
        package,
        trust_store,
    )

    assert result.trusted is False
    assert result.reason == (
        "package signature verification failed"
    )


def test_modified_payload_breaks_signature(
    tmp_path: Path,
) -> None:
    package = create_package(tmp_path)

    private_key, trust_store = create_signer(tmp_path)

    sign_package(package, private_key)

    (package / "payload" / "example.txt").write_text(
        "tampered payload"
    )

    result = verify_package_signature(
        package,
        trust_store,
    )

    assert result.trusted is False
    assert result.reason == (
        "package signature verification failed"
    )


def test_unknown_signer_is_not_trusted(
    tmp_path: Path,
) -> None:
    package = create_package(tmp_path)

    private_key, _ = create_signer(
        tmp_path,
        signer_id="trusted-signer",
    )

    sign_package(
        package,
        private_key,
        signer_id="unknown-signer",
    )

    result = verify_package_signature(
        package,
        tmp_path / "trust",
    )

    assert result.trusted is False
    assert result.signer_id == "unknown-signer"
    assert result.reason == "package signer is not trusted"


def test_malformed_signature_is_not_trusted(
    tmp_path: Path,
) -> None:
    package = create_package(tmp_path)

    _, trust_store = create_signer(tmp_path)

    (package / "signature.json").write_text(
        json.dumps(
            {
                "signer_id": "khan-cloud-test",
                "signature": "%%%not-base64%%%",
            }
        )
    )

    result = verify_package_signature(
        package,
        trust_store,
    )

    assert result.trusted is False
    assert result.reason == (
        "package signature encoding is invalid"
    )


def test_manifest_signed_flag_has_no_authority(
    tmp_path: Path,
) -> None:
    package = create_package(tmp_path)

    _, trust_store = create_signer(tmp_path)

    # create_package deliberately writes signed: true.
    result = verify_package_signature(
        package,
        trust_store,
    )

    assert result.trusted is False
