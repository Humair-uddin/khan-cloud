import sys
from pathlib import Path

import pytest

from kc_installer.engine import (
    CommandExecutionError,
    InstallContext,
    run_health_checks,
)
from kc_installer.models import Manifest
from kc_installer.paths import InstallerPaths
from kc_installer.state import InstallerState


def make_context(
    tmp_path: Path,
    command: list[str],
) -> InstallContext:
    manifest = Manifest.model_validate(
        {
            "feature_pack": {
                "id": "FP-HEALTH",
                "name": "Health Check Test",
                "version": "1.0.0",
            },
            "components": {},
            "health_checks": [
                {
                    "type": "command",
                    "name": "test-health",
                    "command": command,
                }
            ],
        }
    )

    paths = InstallerPaths(
        source_root=tmp_path / "source",
        platform_root=tmp_path,
        runtime_root=tmp_path / "runtime" / "installer",
        state_root=tmp_path / "state" / "installer",
        backup_root=tmp_path / "backups" / "feature-packs",
        package_root=tmp_path / "packages",
    )

    paths.ensure_directories()

    target = tmp_path / "target"
    target.mkdir()

    state = InstallerState(paths.database_path)

    transaction_id = state.begin(
        feature_pack_id="FP-HEALTH",
        feature_pack_version="1.0.0",
        package_path=tmp_path / "package",
        target_path=target,
        backup_path=tmp_path / "backup",
        dry_run=False,
    )

    return InstallContext(
        package_dir=tmp_path / "package",
        target_dir=target,
        manifest=manifest,
        paths=paths,
        state=state,
        transaction_id=transaction_id,
        backup_dir=tmp_path / "backup",
        stage_dir=tmp_path / "stage",
        dry_run=False,
    )


def test_health_check_uses_hardened_executor(
    tmp_path: Path,
) -> None:
    context = make_context(
        tmp_path,
        [
            sys.executable,
            "-c",
            "print('health-ok')",
        ],
    )

    run_health_checks(context)


def test_health_check_failure_propagates_structured_error(
    tmp_path: Path,
) -> None:
    context = make_context(
        tmp_path,
        [
            sys.executable,
            "-c",
            "import sys; print('bad-health', file=sys.stderr); sys.exit(9)",
        ],
    )

    with pytest.raises(CommandExecutionError) as exc_info:
        run_health_checks(context)

    assert exc_info.value.result.returncode == 9
    assert "bad-health" in exc_info.value.result.stderr
