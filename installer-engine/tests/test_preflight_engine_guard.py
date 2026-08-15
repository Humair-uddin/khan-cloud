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


def test_failed_gpu_qualification_does_not_modify_target(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from kc_installer import preflight

    repository = tmp_path / "repository"
    repository.mkdir()

    existing = repository / "important.txt"
    existing.write_text("original")

    package = tmp_path / "package-gpu-guard"
    payload = package / "payload"
    payload.mkdir(parents=True)

    (payload / "important.txt").write_text("changed")

    (package / "manifest.yaml").write_text(
        """
feature_pack:
  id: FP-GAMING-WINDOWS
  name: Windows Gaming Host
  version: 1.0.0

deployment:
  purpose: gaming_host
  platform: windows
  execution_backend: windows_native
  streaming_backend: sunshine

qualification:
  gpu:
    required: true
    qualification_mode: allowlist
    approved_models:
      - NVIDIA GeForce RTX 3080

  driver:
    vendor: nvidia
    required: true
    minimum_version: null
    approved_branches: []

  workloads:
    primary:
      - gaming
    optional_interruptible:
      - ai
      - rendering
      - editing

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
    - name: Dependency That Must Never Be Reached
      command: definitely-not-installed
      classification: remediable
"""
    )

    monkeypatch.setattr(
        preflight,
        "detect_nvidia_gpus",
        lambda: [
            preflight.NvidiaGPU(
                model="NVIDIA GeForce GTX 1080",
                driver_version="576.80",
            )
        ],
    )

    paths = make_paths(
        tmp_path / "khan-cloud-gpu-guard"
    )

    with pytest.raises(
        InstallError,
        match="Preflight compatibility check failed",
    ):
        install(
            package,
            repository,
            paths=paths,
        )

    # Persistent target was never changed.
    assert existing.read_text() == "original"

    # No backup was necessary because component activation
    # never started.
    assert not any(paths.backup_root.iterdir())

    state = InstallerState(paths.database_path)
    transaction = state.installations(limit=1)[0]

    assert transaction["status"] == "preflight_failed"
    assert transaction["current_stage"] == "preflight"

    # No component destinations were ever activated.
    assert state.destinations(
        transaction["transaction_id"]
    ) == []

    journal = state.journal(
        transaction["transaction_id"]
    )

    assert any(
        entry["stage"] == "preflight"
        and entry["status"] == "failed"
        and "gpu_qualification" in entry["message"]
        for entry in journal
    )

    # Critical invariant:
    # dependency processing must never begin after failed
    # machine qualification.
    assert not any(
        entry["stage"] == "dependency"
        for entry in journal
    )

    assert not any(
        entry["stage"] == "remediation_execution"
        for entry in journal
    )
