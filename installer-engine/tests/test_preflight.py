from pathlib import Path

from kc_installer.models import Manifest
from kc_installer.preflight import run_preflight


def manifest_with(**compatibility) -> Manifest:
    return Manifest.model_validate(
        {
            "feature_pack": {
                "id": "FP-PREFLIGHT",
                "name": "Preflight Test",
                "version": "1.0.0",
            },
            "components": {},
            "operations": {
                "require_clean_git": False,
            },
            "compatibility": compatibility,
        }
    )


def test_preflight_accepts_current_architecture(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "kc_installer.preflight.platform.machine",
        lambda: "x86_64",
    )

    manifest = manifest_with(
        architectures=["x86_64"],
    )

    results = run_preflight(manifest, tmp_path)

    assert len(results) == 1
    assert results[0].passed is True


def test_preflight_rejects_wrong_architecture(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "kc_installer.preflight.platform.machine",
        lambda: "arm64",
    )

    manifest = manifest_with(
        architectures=["x86_64"],
    )

    results = run_preflight(manifest, tmp_path)

    assert len(results) == 1
    assert results[0].passed is False


def test_preflight_detects_missing_command(
    tmp_path: Path,
) -> None:
    manifest = Manifest.model_validate(
        {
            "feature_pack": {
                "id": "FP-PREFLIGHT",
                "name": "Preflight Test",
                "version": "1.0.0",
            },
            "components": {},
            "operations": {
                "require_clean_git": False,
            },
            "preflight": {
                "required_commands": [
                    "khan-cloud-command-that-does-not-exist"
                ]
            },
        }
    )

    results = run_preflight(manifest, tmp_path)

    assert len(results) == 1
    assert results[0].passed is False
    assert results[0].actual == "missing"
