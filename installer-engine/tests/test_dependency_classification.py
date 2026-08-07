from pathlib import Path

from kc_installer.models import Manifest
from kc_installer.preflight import classify_dependencies


def build_manifest(classification: str) -> Manifest:
    return Manifest.model_validate(
        {
            "feature_pack": {
                "id": "FP-DEP",
                "name": "Dependency Test",
                "version": "1.0.0",
            },
            "components": {},
            "operations": {
                "require_clean_git": False,
            },
            "preflight": {
                "dependencies": [
                    {
                        "name": "Missing Test Dependency",
                        "command": "kc-command-does-not-exist",
                        "classification": classification,
                    }
                ]
            },
        }
    )


def test_missing_dependency_can_be_remediable() -> None:
    result = classify_dependencies(
        build_manifest("remediable")
    )[0]

    assert result.available is False
    assert result.classification == "remediable"


def test_missing_dependency_can_require_manual_action() -> None:
    result = classify_dependencies(
        build_manifest("manual")
    )[0]

    assert result.available is False
    assert result.classification == "manual"


def test_missing_dependency_can_be_required() -> None:
    result = classify_dependencies(
        build_manifest("required")
    )[0]

    assert result.available is False
    assert result.classification == "required"
