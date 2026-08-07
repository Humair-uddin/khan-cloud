from pathlib import Path

import pytest

from kc_installer.engine import InstallError, install
from kc_installer.paths import InstallerPaths
from kc_installer.state import InstallerState


def make_paths(root: Path) -> InstallerPaths:
    return InstallerPaths(
        source_root=root / "source",
        platform_root=root,
        runtime_root=root / "runtime" / "installer",
        state_root=root / "state" / "installer",
        backup_root=root / "backups" / "feature-packs",
        package_root=root / "packages",
    )


def test_failed_preflight_does_not_modify_target(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()

    existing = repository / "important.txt"
    existing.write_text("original")

    package = tmp_path / "package"
    payload = package / "payload"
    payload.mkdir(parents=True)

    (payload / "important.txt").write_text("changed")

    (package / "manifest.yaml").write_text(
        """
feature_pack:
  id: FP-PREFLIGHT-GUARD
  name: Preflight Guard
  version: 1.0.0

components:
  important:
    enabled: true
    source: payload/important.txt
    destination: important.txt

operations:
  require_clean_git: false
  create_backup: true
  run_health_checks: false
  rollback_on_failure: true

compatibility:
  architectures:
    - definitely-not-this-architecture
"""
    )

    paths = make_paths(tmp_path / "khan-cloud")

    with pytest.raises(
        InstallError,
        match="Preflight compatibility check failed",
    ):
        install(
            package,
            repository,
            paths=paths,
        )

    assert existing.read_text() == "original"

    assert not any(paths.backup_root.iterdir())

    state = InstallerState(paths.database_path)
    installations = state.installations(limit=1)

    assert len(installations) == 1
    assert installations[0]["status"] == "preflight_failed"
    assert installations[0]["current_stage"] == "preflight"

    assert state.destinations(
        installations[0]["transaction_id"]
    ) == []
