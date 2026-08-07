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


def make_package(
    tmp_path: Path,
    classification: str,
) -> Path:
    package = tmp_path / f"package-{classification}"
    payload = package / "payload"
    payload.mkdir(parents=True)

    (payload / "important.txt").write_text("changed")

    (package / "manifest.yaml").write_text(
        f"""
feature_pack:
  id: FP-DEP-{classification.upper()}
  name: Dependency Guard
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

preflight:
  dependencies:
    - name: Missing Dependency
      command: kc-command-that-does-not-exist
      classification: {classification}
"""
    )

    return package


def test_remediable_dependency_does_not_block(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()

    target = repository / "important.txt"
    target.write_text("original")

    paths = make_paths(tmp_path / "khan-cloud")

    install(
        make_package(tmp_path, "remediable"),
        repository,
        dry_run=True,
        paths=paths,
    )

    assert target.read_text() == "original"

    state = InstallerState(paths.database_path)
    transaction = state.installations(limit=1)[0]
    journal = state.journal(transaction["transaction_id"])

    assert any(
        entry["stage"] == "dependency"
        and entry["status"] == "remediable"
        for entry in journal
    )


@pytest.mark.parametrize(
    "classification",
    ["required", "manual"],
)
def test_blocking_dependency_does_not_modify_target(
    tmp_path: Path,
    classification: str,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()

    target = repository / "important.txt"
    target.write_text("original")

    paths = make_paths(tmp_path / f"khan-cloud-{classification}")

    with pytest.raises(
        InstallError,
        match="Dependency validation failed",
    ):
        install(
            make_package(tmp_path, classification),
            repository,
            paths=paths,
        )

    assert target.read_text() == "original"
    assert not any(paths.backup_root.iterdir())

    state = InstallerState(paths.database_path)
    transaction = state.installations(limit=1)[0]

    assert transaction["status"] == "dependency_blocked"
    assert transaction["current_stage"] == "dependency"
