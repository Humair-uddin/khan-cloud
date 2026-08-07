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


def test_dry_run_does_not_modify_destination(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()

    package = tmp_path / "package"
    (package / "payload").mkdir(parents=True)
    (package / "payload" / "demo.txt").write_text("new")

    (package / "manifest.yaml").write_text(
        """
feature_pack:
  id: FP-X
  name: Test
  version: 1.0.0

components:
  demo:
    enabled: true
    source: payload/demo.txt
    destination: demo.txt

operations:
  require_clean_git: false
  create_backup: true
  rollback_on_failure: true
  run_health_checks: false
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

    assert paths.database_path.exists()
    assert str(paths.database_path).startswith(str(tmp_path))
