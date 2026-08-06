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
