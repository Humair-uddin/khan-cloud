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


def test_dry_run_is_persisted_in_journal(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()

    package = tmp_path / "package"
    (package / "payload").mkdir(parents=True)
    (package / "payload" / "demo.txt").write_text("demo")

    (package / "manifest.yaml").write_text(
        """
feature_pack:
  id: FP-JOURNAL
  name: Journal Test
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

    report = install(
        package,
        repository,
        dry_run=True,
        paths=paths,
    )

    assert report.exists()
    assert not (repository / "demo.txt").exists()

    state = InstallerState(paths.database_path)

    import sqlite3

    with sqlite3.connect(paths.database_path) as db:
        row = db.execute(
            """
            SELECT transaction_id, status, current_stage
            FROM installations
            ORDER BY started_at DESC
            LIMIT 1
            """
        ).fetchone()

    assert row is not None
    transaction_id, status, current_stage = row

    assert status == "dry_run_success"
    assert current_stage == "completed"

    stages = [
        item["stage"]
        for item in state.journal(transaction_id)
    ]

    assert stages == [
        "started",
        "validated",
        "staged",
        "completed",
    ]
