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


def test_manifest_accepts_qualification_policy_snapshot():
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
        "qualification": {
            "gpu": {
                "required": True,
                "qualification_mode": "allowlist",
                "approved_models": [
                    "NVIDIA GeForce RTX 3080",
                ],
            },
            "driver": {
                "vendor": "nvidia",
                "required": True,
                "minimum_version": None,
                "approved_branches": [],
            },
            "workloads": {
                "primary": ["gaming"],
                "optional_interruptible": [
                    "ai",
                    "rendering",
                    "editing",
                ],
            },
        },
        "components": {},
    })

    assert manifest.qualification is not None

    assert manifest.qualification.gpu.required is True
    assert (
        manifest.qualification.gpu.qualification_mode
        == "allowlist"
    )
    assert (
        "NVIDIA GeForce RTX 3080"
        in manifest.qualification.gpu.approved_models
    )

    assert manifest.qualification.driver.vendor == "nvidia"
    assert manifest.qualification.driver.required is True

    assert manifest.qualification.workloads.primary == ["gaming"]
    assert (
        "ai"
        in manifest.qualification.workloads.optional_interruptible
    )


def test_manifest_qualification_snapshot_is_optional_for_legacy_packs():
    from kc_installer.models import Manifest

    manifest = Manifest.model_validate({
        "feature_pack": {
            "id": "FP-LEGACY",
            "name": "Legacy Pack",
            "version": "1.0.0",
        },
        "components": {},
    })

    assert manifest.qualification is None


def test_manifest_accepts_image_recipe_artifact_sources():
    from kc_installer.models import Manifest

    manifest = Manifest.model_validate({
        "feature_pack": {"id":"FP-GAMING","name":"Gaming","version":"1"},
        "components": {},
        "image_recipe": {
            "id": "gaming-win11",
            "version": "2026.08.1",
            "artifacts": [
                {
                    "id": "khan-vdd", "version": "1.0.0", "stage": "image_build",
                    "source": {"type": "khan_artifact", "url": "https://artifacts.example/vdd.zip"},
                    "sha256": "a" * 64,
                },
                {
                    "id": "nvidia-gpup", "version": "host", "stage": "host_specific",
                    "source": {"type": "host_projection"},
                },
            ],
        },
    })
    assert manifest.image_recipe is not None
    assert manifest.image_recipe.artifacts[1].source.type == "host_projection"


def test_manifest_rejects_unpinned_download_and_wrong_host_projection_stage(tmp_path: Path):
    (tmp_path / "manifest.yaml").write_text('''
feature_pack:
  id: FP-GAMING
  name: Gaming
  version: "1"
components: {}
image_recipe:
  id: gaming-win11
  version: 2026.08.1
  artifacts:
    - id: khan-vdd
      version: 1.0.0
      stage: image_build
      source:
        type: khan_artifact
        url: https://artifacts.example/vdd.zip
    - id: nvidia-gpup
      version: host
      stage: image_build
      source:
        type: host_projection
''')
    manifest = load_manifest(tmp_path)
    errors = validate_manifest_files(tmp_path, manifest)
    assert any("pinned SHA-256" in error for error in errors)
    assert any("host_specific" in error for error in errors)
