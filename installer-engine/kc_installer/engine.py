from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from kc_installer.lock import InstallerLock
from kc_installer.manifest import load_manifest, validate_manifest_files
from kc_installer.models import Manifest
from kc_installer.paths import InstallerPaths
from kc_installer.state import InstallerState


class InstallError(RuntimeError):
    pass


@dataclass
class InstallContext:
    package_dir: Path
    target_dir: Path
    manifest: Manifest
    paths: InstallerPaths
    state: InstallerState
    transaction_id: str
    backup_dir: Path
    stage_dir: Path
    dry_run: bool


def command_output(command: list[str]) -> str:
    return subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def ensure_clean_git(target: Path) -> None:
    status = command_output(
        ["git", "-C", str(target), "status", "--short"]
    )
    if status:
        raise InstallError(
            "Git working tree is not clean:\n" + status
        )


def prepare_context(
    package_dir: Path,
    target_dir: Path,
    *,
    dry_run: bool,
    paths: InstallerPaths | None = None,
) -> InstallContext:
    active_paths = paths or InstallerPaths.from_environment()
    active_paths.ensure_directories()

    manifest = load_manifest(package_dir)
    errors = validate_manifest_files(package_dir, manifest)
    if errors:
        raise InstallError("\n".join(errors))

    if manifest.operations.require_clean_git:
        ensure_clean_git(target_dir)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")

    backup_dir = (
        active_paths.backup_root
        / f"{manifest.feature_pack.id.lower()}-{stamp}"
    )

    stage_dir = Path(
        tempfile.mkdtemp(
            prefix=f"{manifest.feature_pack.id.lower()}-stage-",
            dir=active_paths.temp_dir,
        )
    )

    state = InstallerState(active_paths.database_path)

    transaction_id = state.begin(
        feature_pack_id=manifest.feature_pack.id,
        feature_pack_version=manifest.feature_pack.version,
        package_path=package_dir,
        target_path=target_dir,
        backup_path=backup_dir,
        dry_run=dry_run,
    )

    state.record(
        transaction_id,
        "validated",
        "success",
        "Manifest and repository validation passed.",
    )

    return InstallContext(
        package_dir=package_dir,
        target_dir=target_dir,
        manifest=manifest,
        paths=active_paths,
        state=state,
        transaction_id=transaction_id,
        backup_dir=backup_dir,
        stage_dir=stage_dir,
        dry_run=dry_run,
    )


def copy_component_to_stage(
    context: InstallContext,
    name: str,
) -> tuple[Path, Path]:
    component = context.manifest.components[name]

    if component.source is None:
        raise InstallError(
            f"Component {name!r} has no source path."
        )

    if component.destination is None:
        raise InstallError(
            f"Component {name!r} has no destination path."
        )

    source = (context.package_dir / component.source).resolve()
    staged = context.stage_dir / component.destination
    destination = (
        context.target_dir / component.destination
    ).resolve()

    try:
        destination.relative_to(context.target_dir)
    except ValueError as exc:
        raise InstallError(
            f"Unsafe destination outside target repository: {destination}"
        ) from exc

    if source.is_dir():
        shutil.copytree(source, staged)
    else:
        staged.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, staged)

    return staged, destination


def backup_destination(
    context: InstallContext,
    destination: Path,
) -> None:
    if not destination.exists():
        return

    relative = destination.relative_to(context.target_dir)
    backup_target = context.backup_dir / relative
    backup_target.parent.mkdir(parents=True, exist_ok=True)

    if destination.is_dir():
        shutil.copytree(destination, backup_target)
    else:
        shutil.copy2(destination, backup_target)


def activate_component(
    staged: Path,
    destination: Path,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)

    if destination.exists():
        if destination.is_dir():
            shutil.rmtree(destination)
        else:
            destination.unlink()

    shutil.move(str(staged), str(destination))


def rollback(
    context: InstallContext,
    destinations: list[Path],
) -> None:
    for destination in reversed(destinations):
        if destination.exists():
            if destination.is_dir():
                shutil.rmtree(destination)
            else:
                destination.unlink()

        relative = destination.relative_to(context.target_dir)
        backup = context.backup_dir / relative

        if backup.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)

            if backup.is_dir():
                shutil.copytree(backup, destination)
            else:
                shutil.copy2(backup, destination)


def run_health_checks(context: InstallContext) -> None:
    for check in context.manifest.health_checks:
        subprocess.run(
            check.command,
            check=True,
            cwd=context.target_dir,
        )


def create_report(
    context: InstallContext,
    status: str,
    destinations: list[Path],
    message: str = "",
) -> Path:
    context.paths.reports_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    report_path = context.paths.reports_dir / (
        f"{context.manifest.feature_pack.id.lower()}-"
        f"{context.transaction_id}.json"
    )

    report = {
        "transaction_id": context.transaction_id,
        "feature_pack": (
            context.manifest.feature_pack.model_dump()
        ),
        "status": status,
        "dry_run": context.dry_run,
        "package": str(context.package_dir),
        "target": str(context.target_dir),
        "destinations": [str(item) for item in destinations],
        "backup": str(context.backup_dir),
        "runtime": str(context.paths.runtime_root),
        "state": str(context.paths.state_root),
        "message": message,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }

    report_path.write_text(
        json.dumps(report, indent=2, default=str)
    )

    return report_path


def _install_locked(
    package_dir: Path,
    target_dir: Path,
    *,
    dry_run: bool = False,
    paths: InstallerPaths | None = None,
) -> Path:
    context = prepare_context(
        package_dir.resolve(),
        target_dir.resolve(),
        dry_run=dry_run,
        paths=paths,
    )

    destinations: list[Path] = []

    try:
        enabled_components = [
            name
            for name, specification
            in context.manifest.components.items()
            if specification.enabled
        ]

        staged_items: list[tuple[Path, Path]] = []

        for name in enabled_components:
            staged, destination = copy_component_to_stage(
                context,
                name,
            )
            staged_items.append((staged, destination))
            destinations.append(destination)

        context.state.record(
            context.transaction_id,
            "staged",
            "success",
            f"Staged {len(staged_items)} component(s).",
        )

        if dry_run:
            context.state.finish(
                context.transaction_id,
                status="dry_run_success",
                stage="completed",
            )
            return create_report(
                context,
                "dry_run_success",
                destinations,
            )

        if context.manifest.operations.create_backup:
            for destination in destinations:
                backup_destination(context, destination)

        context.state.record(
            context.transaction_id,
            "backup",
            "success",
            str(context.backup_dir),
        )

        for staged, destination in staged_items:
            activate_component(staged, destination)

        context.state.record(
            context.transaction_id,
            "activated",
            "success",
            f"Activated {len(staged_items)} component(s).",
        )

        if context.manifest.operations.run_health_checks:
            context.state.record(
                context.transaction_id,
                "health_check",
                "started",
            )
            run_health_checks(context)
            context.state.record(
                context.transaction_id,
                "health_check",
                "success",
            )

        context.state.finish(
            context.transaction_id,
            status="success",
            stage="completed",
        )

        return create_report(
            context,
            "success",
            destinations,
        )

    except Exception as exc:
        context.state.record(
            context.transaction_id,
            "failed",
            "failed",
            str(exc),
        )

        if (
            not dry_run
            and context.manifest.operations.rollback_on_failure
        ):
            context.state.record(
                context.transaction_id,
                "rollback",
                "started",
            )

            try:
                rollback(context, destinations)
            except Exception as rollback_exc:
                context.state.finish(
                    context.transaction_id,
                    status="rollback_failed",
                    stage="rollback",
                    error_message=(
                        f"Original error: {exc}; "
                        f"Rollback error: {rollback_exc}"
                    ),
                )
                create_report(
                    context,
                    "rollback_failed",
                    destinations,
                    str(rollback_exc),
                )
                raise

            context.state.record(
                context.transaction_id,
                "rollback",
                "success",
            )

        context.state.finish(
            context.transaction_id,
            status="failed",
            stage="failed",
            error_message=str(exc),
        )

        create_report(
            context,
            "failed",
            destinations,
            str(exc),
        )
        raise

    finally:
        shutil.rmtree(
            context.stage_dir,
            ignore_errors=True,
        )


def install(
    package_dir: Path,
    target_dir: Path,
    *,
    dry_run: bool = False,
    paths: InstallerPaths | None = None,
) -> Path:
    active_paths = paths or InstallerPaths.from_environment()
    active_paths.ensure_directories()

    with InstallerLock(active_paths.installation_lock_path):
        return _install_locked(
            package_dir,
            target_dir,
            dry_run=dry_run,
            paths=active_paths,
        )
