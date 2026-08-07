import sqlite3
from pathlib import Path

from kc_installer.engine import install
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


def test_engine_updates_transaction_heartbeat(
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
  id: FP-HEARTBEAT
  name: Heartbeat Test
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

    install(
        package,
        repository,
        dry_run=True,
        paths=paths,
    )

    with sqlite3.connect(paths.database_path) as db:
        row = db.execute(
            """
            SELECT started_at, last_heartbeat_at, status
            FROM installations
            ORDER BY started_at DESC
            LIMIT 1
            """
        ).fetchone()

    assert row is not None

    started_at, last_heartbeat_at, status = row

    assert last_heartbeat_at is not None
    assert last_heartbeat_at >= started_at
    assert status == "dry_run_success"
