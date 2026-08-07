from pathlib import Path

from kc_installer.engine import install
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


def test_engine_persists_destination_plan(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()

    existing = repository / "existing.txt"
    existing.write_text("old")

    package = tmp_path / "package"
    payload = package / "payload"
    payload.mkdir(parents=True)

    (payload / "existing.txt").write_text("new-existing")
    (payload / "new.txt").write_text("new-file")

    (package / "manifest.yaml").write_text(
        """
feature_pack:
  id: FP-DEST-ENGINE
  name: Destination Recording Test
  version: 1.0.0

components:
  existing:
    enabled: true
    source: payload/existing.txt
    destination: existing.txt

  new:
    enabled: true
    source: payload/new.txt
    destination: new.txt

operations:
  require_clean_git: false
  create_backup: true
  run_health_checks: false
  rollback_on_failure: true
"""
    )

    paths = make_paths(tmp_path / "khan-cloud")

    install(
        package,
        repository,
        dry_run=True,
        paths=paths,
    )

    state = InstallerState(paths.database_path)
    installations = state.installations(limit=1)

    assert len(installations) == 1

    transaction_id = installations[0]["transaction_id"]
    destinations = state.destinations(transaction_id)

    assert len(destinations) == 2

    assert destinations[0]["destination_path"] == str(existing)
    assert destinations[0]["existed_before"] == 1

    assert destinations[1]["destination_path"] == str(
        repository / "new.txt"
    )
    assert destinations[1]["existed_before"] == 0
