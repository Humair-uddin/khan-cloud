from pathlib import Path

from kc_installer.manifest import load_manifest, validate_manifest_files


def test_manifest_detects_existing_component(tmp_path: Path) -> None:
    (tmp_path / "payload").mkdir()
    (tmp_path / "payload" / "file.txt").write_text("ok")
    (tmp_path / "manifest.yaml").write_text(
        """
feature_pack:
  id: FP-X
  name: Test
  version: 1.0.0
components:
  sample:
    enabled: true
    source: payload/file.txt
    destination: sample/file.txt
"""
    )

    manifest = load_manifest(tmp_path)
    assert validate_manifest_files(tmp_path, manifest) == []


def test_manifest_detects_missing_component(tmp_path: Path) -> None:
    (tmp_path / "manifest.yaml").write_text(
        """
feature_pack:
  id: FP-X
  name: Test
  version: 1.0.0
components:
  sample:
    enabled: true
    source: payload/missing.txt
    destination: sample/file.txt
"""
    )

    manifest = load_manifest(tmp_path)
    errors = validate_manifest_files(tmp_path, manifest)
    assert errors


def test_manifest_accepts_deployment_target_metadata():
    from kc_installer.models import Manifest

    manifest = Manifest.model_validate({
        "feature_pack": {
            "id": "FP-GAMING-WINDOWS",
            "name": "Windows Gaming Host",
            "version": "1.0.0",
        },
        "deployment": {
            "purpose": "gaming_host",
            "platform": "windows",
            "execution_backend": "windows_native",
            "streaming_backend": "sunshine",
        },
        "components": {},
    })

    assert manifest.deployment.purpose == "gaming_host"
    assert manifest.deployment.platform == "windows"
    assert manifest.deployment.execution_backend == "windows_native"
    assert manifest.deployment.streaming_backend == "sunshine"


def test_manifest_deployment_metadata_is_optional_for_existing_feature_packs():
    from kc_installer.models import Manifest

    manifest = Manifest.model_validate({
        "feature_pack": {
            "id": "FP-LEGACY",
            "name": "Legacy Pack",
            "version": "1.0.0",
        },
        "components": {},
    })

    assert manifest.deployment is None
