from __future__ import annotations

import hashlib
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
from kc_installer.preflight import classify_dependencies, run_preflight
from kc_installer.state import InstallerState


class InstallError(RuntimeError):
    pass


def checksum_path(path: Path) -> str:
    digest = hashlib.sha256()

    if path.is_file():
        with path.open("rb") as handle:
            for chunk in iter(
                lambda: handle.read(1024 * 1024),
                b"",
            ):
                digest.update(chunk)

        return digest.hexdigest()

    if path.is_dir():
        for item in sorted(
            (entry for entry in path.rglob("*") if entry.is_file()),
            key=lambda entry: str(entry.relative_to(path)),
        ):
            relative = str(item.relative_to(path)).encode("utf-8")
            digest.update(relative)
            digest.update(b"\0")

            with item.open("rb") as handle:
                for chunk in iter(
                    lambda: handle.read(1024 * 1024),
                    b"",
                ):
                    digest.update(chunk)

        return digest.hexdigest()

    raise InstallError(
        f"Cannot checksum missing path: {path}"
    )


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

    preflight_results = run_preflight(
        manifest,
        target_dir,
    )

    failed_preflight = [
        result
        for result in preflight_results
        if not result.passed
    ]

    for result in preflight_results:
        state.record(
            transaction_id,
            "preflight",
            "success" if result.passed else "failed",
            (
                f"{result.name}: actual={result.actual}; "
                f"required={result.required}"
            ),
        )

    if failed_preflight:
        message = "; ".join(
            (
                f"{result.name}: actual={result.actual}, "
                f"required={result.required}"
            )
            for result in failed_preflight
        )

        state.finish(
            transaction_id,
            status="preflight_failed",
            stage="preflight",
            error_message=message,
        )

        raise InstallError(
            "Preflight compatibility check failed: " + message
        )

    dependency_results = classify_dependencies(manifest)

    dependency_failures: list[str] = []

    for dependency in dependency_results:
        if dependency.available:
            state.record(
                transaction_id,
                "dependency",
                "success",
                (
                    f"{dependency.name}: available "
                    f"({dependency.command})"
                ),
            )
            continue

        if dependency.classification == "remediable":
            state.record(
                transaction_id,
                "dependency",
                "remediable",
                (
                    f"{dependency.name}: missing but approved "
                    "for future automatic remediation."
                ),
            )
            continue

        if dependency.classification == "manual":
            message = (
                f"{dependency.name}: manual administrator "
                "action required."
            )
            state.record(
                transaction_id,
                "dependency",
                "manual_required",
                message,
            )
            dependency_failures.append(message)
            continue

        message = (
            f"{dependency.name}: required dependency is missing."
        )
        state.record(
            transaction_id,
            "dependency",
            "failed",
            message,
        )
        dependency_failures.append(message)

    if dependency_failures:
        message = "; ".join(dependency_failures)

        state.finish(
            transaction_id,
            status="dependency_blocked",
            stage="dependency",
            error_message=message,
        )

        raise InstallError(
            "Dependency validation failed: " + message
        )

    state.record(
        transaction_id,
        "preflight",
        "success",
        "All compatibility and dependency checks passed.",
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

        context.state.record_destinations(
            context.transaction_id,
            [
                (destination, destination.exists())
                for destination in destinations
            ],
        )

        context.state.heartbeat(context.transaction_id)
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
                existed_before = destination.exists()

                backup_destination(context, destination)

                if existed_before:
                    relative = destination.relative_to(
                        context.target_dir
                    )
                    backup = context.backup_dir / relative

                    if not backup.exists():
                        raise InstallError(
                            "Backup creation failed for "
                            f"{destination}"
                        )

                    context.state.record_backup_checksum(
                        context.transaction_id,
                        destination,
                        checksum_path(backup),
                    )

        context.state.heartbeat(context.transaction_id)
        context.state.record(
            context.transaction_id,
            "backup",
            "success",
            str(context.backup_dir),
        )

        for staged, destination in staged_items:
            activate_component(staged, destination)

        context.state.heartbeat(context.transaction_id)
        context.state.record(
            context.transaction_id,
            "activated",
            "success",
            f"Activated {len(staged_items)} component(s).",
        )

        if context.manifest.operations.run_health_checks:
            context.state.heartbeat(context.transaction_id)
            context.state.record(
                context.transaction_id,
                "health_check",
                "started",
            )
            run_health_checks(context)
            context.state.heartbeat(context.transaction_id)
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


def recover_transaction(
    transaction_id: str,
    *,
    stale_after_seconds: int = 300,
    paths: InstallerPaths | None = None,
) -> dict[str, object]:
    active_paths = paths or InstallerPaths.from_environment()
    active_paths.ensure_directories()

    state = InstallerState(active_paths.database_path)

    with InstallerLock(active_paths.installation_lock_path):
        matches = [
            item
            for item in state.classify_incomplete(
                stale_after_seconds=stale_after_seconds,
            )
            if item["transaction_id"] == transaction_id
        ]

        if not matches:
            raise InstallError(
                "Transaction is not currently incomplete or was not found."
            )

        transaction = matches[0]

        if transaction["classification"] == "active":
            raise InstallError(
                "Recovery refused: transaction is still active."
            )

        if transaction["classification"] not in {
            "interrupted",
            "stale",
        }:
            raise InstallError(
                "Recovery refused: transaction is not safely recoverable."
            )

        target_root = Path(
            transaction["target_path"]
        ).resolve()

        backup_root = Path(
            transaction["backup_path"]
        ).resolve()

        destinations = state.destinations(transaction_id)

        if not destinations:
            raise InstallError(
                "Recovery refused: transaction has no recorded destinations."
            )

        validated: list[tuple[Path, Path, bool]] = []

        for item in destinations:
            destination = Path(
                item["destination_path"]
            ).resolve()

            try:
                relative = destination.relative_to(target_root)
            except ValueError as exc:
                raise InstallError(
                    "Recovery refused: recorded destination is "
                    f"outside target root: {destination}"
                ) from exc

            backup = (backup_root / relative).resolve()

            try:
                backup.relative_to(backup_root)
            except ValueError as exc:
                raise InstallError(
                    "Recovery refused: computed backup path is unsafe."
                ) from exc

            existed_before = bool(item["existed_before"])

            if existed_before and not backup.exists():
                raise InstallError(
                    "Recovery refused: required backup is missing for "
                    f"{destination}"
                )

            if existed_before:
                recorded_checksum = item.get("backup_checksum")

                if not recorded_checksum:
                    raise InstallError(
                        "Recovery refused: required backup checksum "
                        f"is missing for {destination}"
                    )

                actual_checksum = checksum_path(backup)

                if actual_checksum != recorded_checksum:
                    raise InstallError(
                        "Recovery refused: backup integrity check "
                        f"failed for {destination}"
                    )

            validated.append(
                (
                    destination,
                    backup,
                    existed_before,
                )
            )

        state.mark_recovery_requested(transaction_id)

        state.record(
            transaction_id,
            "recovery_started",
            "started",
            "Validated rollback recovery started.",
        )

        try:
            for destination, backup, existed_before in reversed(
                validated
            ):
                if destination.exists():
                    if destination.is_dir():
                        shutil.rmtree(destination)
                    else:
                        destination.unlink()

                if existed_before:
                    destination.parent.mkdir(
                        parents=True,
                        exist_ok=True,
                    )

                    if backup.is_dir():
                        shutil.copytree(
                            backup,
                            destination,
                        )
                    else:
                        shutil.copy2(
                            backup,
                            destination,
                        )

            state.finish(
                transaction_id,
                status="recovered",
                stage="recovered",
            )

        except Exception as exc:
            state.finish(
                transaction_id,
                status="recovery_failed",
                stage="recovery_failed",
                error_message=str(exc),
            )
            raise

        return {
            "status": "recovered",
            "transaction_id": transaction_id,
            "restored_destinations": len(validated),
            "target_path": str(target_root),
            "backup_path": str(backup_root),
        }
