from pathlib import Path

from kc_installer.engine import install


def test_dry_run_does_not_modify_destination(tmp_path: Path) -> None:
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
"""
    )

    report = install(package, repository, dry_run=True)
    assert report.exists()
    assert not (repository / "demo.txt").exists()
