from pathlib import Path

import pytest

from kc_installer.engine import install
from kc_installer.lock import InstallerLock, InstallerLockError
from kc_installer.paths import InstallerPaths


def make_paths(root: Path) -> InstallerPaths:
    return InstallerPaths(
        source_root=root / "source",
        platform_root=root,
        runtime_root=root / "runtime" / "installer",
        state_root=root / "state" / "installer",
        backup_root=root / "backups" / "feature-packs",
        package_root=root / "packages",
    )


def test_install_rejects_when_global_lock_is_held(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()

    package = tmp_path / "package"
    (package / "payload").mkdir(parents=True)
    (package / "payload" / "demo.txt").write_text("demo")

    (package / "manifest.yaml").write_text(
        """
feature_pack:
  id: FP-LOCK
  name: Lock Test
  version: 1.0.0

components:
  demo:
    enabled: true
    source: payload/demo.txt
    destination: demo.txt

operations:
  require_clean_git: false
  create_backup: true
  run_health_checks: false
  rollback_on_failure: true
"""
    )

    paths = make_paths(tmp_path / "khan-cloud")
    paths.ensure_directories()

    with InstallerLock(paths.installation_lock_path):
        with pytest.raises(InstallerLockError):
            install(
                package,
                repository,
                dry_run=True,
                paths=paths,
            )

    assert not (repository / "demo.txt").exists()
