from pathlib import Path

from kc_installer.paths import InstallerPaths


def test_installer_paths_can_be_overridden(
    monkeypatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "khan-cloud"

    monkeypatch.setenv("KHAN_CLOUD_ROOT", str(root))

    paths = InstallerPaths.from_environment()
    paths.ensure_directories()

    assert paths.source_root == root / "source"
    assert paths.runtime_root == root / "runtime" / "installer"
    assert paths.state_root == root / "state" / "installer"
    assert paths.backup_root == root / "backups" / "feature-packs"

    assert paths.reports_dir.is_dir()
    assert paths.temp_dir.is_dir()
    assert paths.history_dir.is_dir()
    assert paths.checkpoint_dir.is_dir()
    assert paths.lock_dir.is_dir()
