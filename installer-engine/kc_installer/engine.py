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
from kc_installer.preflight import (
    build_remediation_plan,
    evaluate_remediation_policy,
    RemediationPolicyDecision,
    classify_dependencies,
    run_preflight,
)
from kc_installer.state import InstallerState
from kc_installer.trust import verify_package_signature


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


@dataclass(frozen=True)
class CommandExecutionResult:
    command: list[str]
    returncode: int | None
    stdout: str
    stderr: str
    timed_out: bool = False


class CommandExecutionError(InstallError):
    def __init__(
        self,
        message: str,
        result: CommandExecutionResult,
    ) -> None:
        super().__init__(message)
        self.result = result


MAX_COMMAND_OUTPUT_CHARS = 65536

def _sanitize_command_output(value: str) -> str:
    import re
    redacted = re.sub(
        r"(?i)(token|password|secret|api[_-]?key)(\s*[=:]\s*)[^\s]+",
        r"\1\2[REDACTED]",
        value,
    )
    if len(redacted) > MAX_COMMAND_OUTPUT_CHARS:
        omitted = len(redacted) - MAX_COMMAND_OUTPUT_CHARS
        redacted = redacted[:MAX_COMMAND_OUTPUT_CHARS] + (
            f"\n...[TRUNCATED {omitted} CHARS]"
        )
    return redacted


def execute_command(
    command: list[str],
    *,
    cwd: Path,
    timeout_seconds: float = 300.0,
) -> CommandExecutionResult:
    if not command:
        raise ValueError("Command must not be empty.")

    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            shell=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""

        if isinstance(stdout, bytes):
            stdout = stdout.decode(errors="replace")

        if isinstance(stderr, bytes):
            stderr = stderr.decode(errors="replace")

        result = CommandExecutionResult(
            command=list(command),
            returncode=None,
            stdout=_sanitize_command_output(stdout),
            stderr=_sanitize_command_output(stderr),
            timed_out=True,
        )

        raise CommandExecutionError(
            (
                "Command timed out after "
                f"{timeout_seconds} seconds: {command!r}"
            ),
            result,
        ) from exc

    result = CommandExecutionResult(
        command=list(command),
        returncode=completed.returncode,
        stdout=_sanitize_command_output(completed.stdout),
        stderr=_sanitize_command_output(completed.stderr),
    )

    if completed.returncode != 0:
        raise CommandExecutionError(
            (
                f"Command failed with exit code "
                f"{completed.returncode}: {command!r}"
            ),
            result,
        )

    return result


@dataclass(frozen=True)
class RemediationExecutionResult:
    dependency_name: str
    dependency_command: str
    command_result: CommandExecutionResult
    verified: bool


class RemediationExecutionError(InstallError):
    def __init__(
        self,
        message: str,
        *,
        command_result: CommandExecutionResult | None = None,
    ) -> None:
        super().__init__(message)
        self.command_result = command_result


def execute_remediation(
    decision: RemediationPolicyDecision,
    manifest: Manifest,
    *,
    cwd: Path,
    timeout_seconds: float = 300.0,
) -> RemediationExecutionResult:
    """
    Execute one already-authorized remediation decision and verify
    that its declared dependency becomes available.

    This function does not evaluate trust or policy itself. It only
    accepts an already-produced policy decision and fails closed when
    that decision is not eligible.
    """

    if not decision.eligible:
        raise RemediationExecutionError(
            (
                f"Remediation is not eligible for "
                f"{decision.dependency_name}: {decision.reason}"
            )
        )

    if decision.action_type != "command":
        raise RemediationExecutionError(
            (
                "Unsupported remediation action type: "
                f"{decision.action_type}"
            )
        )

    dependency = next(
        (
            item
            for item in manifest.preflight.dependencies
            if item.name == decision.dependency_name
        ),
        None,
    )

    if dependency is None:
        raise RemediationExecutionError(
            (
                "Dependency not found in manifest: "
                f"{decision.dependency_name}"
            )
        )

    command_result = execute_command(
        list(decision.command),
        cwd=cwd,
        timeout_seconds=timeout_seconds,
    )

    import shutil as _shutil

    verified = _shutil.which(dependency.command) is not None

    if not verified:
        raise RemediationExecutionError(
            (
                f"Remediation command succeeded but dependency "
                f"{decision.dependency_name!r} is still unavailable "
                f"({dependency.command})."
            ),
            command_result=command_result,
        )

    return RemediationExecutionResult(
        dependency_name=decision.dependency_name,
        dependency_command=dependency.command,
        command_result=command_result,
        verified=True,
    )


def execute_remediation_attempt(
    *,
    state: InstallerState,
    transaction_id: str,
    position: int,
    decision: RemediationPolicyDecision,
    manifest: Manifest,
    cwd: Path,
    timeout_seconds: float = 300.0,
) -> RemediationExecutionResult:
    """
    Execute one remediation decision with mandatory persisted
    attempt lifecycle and audit recording.

    This function is intentionally not wired into install().
    """

    attempt_id = state.begin_remediation_attempt(
        transaction_id,
        position,
    )

    try:
        result = execute_remediation(
            decision,
            manifest,
            cwd=cwd,
            timeout_seconds=timeout_seconds,
        )

    except RemediationExecutionError as exc:
        command_result = exc.command_result

        status = "blocked"

        if command_result is not None:
            status = (
                "timeout"
                if command_result.timed_out
                else "failed"
            )

        state.finish_remediation_attempt(
            attempt_id,
            status=status,
            return_code=(
                command_result.returncode
                if command_result is not None
                else None
            ),
            timed_out=(
                command_result.timed_out
                if command_result is not None
                else False
            ),
            stdout=(
                command_result.stdout
                if command_result is not None
                else ""
            ),
            stderr=(
                command_result.stderr
                if command_result is not None
                else ""
            ),
            verified=False,
            error_message=str(exc),
        )

        raise

    except CommandExecutionError as exc:
        result_data = exc.result

        state.finish_remediation_attempt(
            attempt_id,
            status=(
                "timeout"
                if result_data.timed_out
                else "failed"
            ),
            return_code=result_data.returncode,
            timed_out=result_data.timed_out,
            stdout=result_data.stdout,
            stderr=result_data.stderr,
            verified=False,
            error_message=str(exc),
        )

        raise

    except Exception as exc:
        state.finish_remediation_attempt(
            attempt_id,
            status="failed",
            verified=False,
            error_message=str(exc),
        )
        raise

    state.finish_remediation_attempt(
        attempt_id,
        status="success",
        return_code=result.command_result.returncode,
        timed_out=result.command_result.timed_out,
        stdout=result.command_result.stdout,
        stderr=result.command_result.stderr,
        verified=result.verified,
    )

    return result


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

    trust_result = verify_package_signature(
        package_dir,
        active_paths.trust_store_dir,
    )
    state.record_package_trust(
        transaction_id,
        trusted=trust_result.trusted,
        signer_id=trust_result.signer_id,
        package_digest=trust_result.package_digest,
        trust_reason=trust_result.reason,
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

    remediation_plan = build_remediation_plan(manifest)

    remediation_decisions = evaluate_remediation_policy(
        manifest,
        dry_run=dry_run,
        trusted_package=trust_result.trusted,
    )

    decision_by_dependency = {
        decision.dependency_name: decision
        for decision in remediation_decisions
    }

    state.record_remediation_plan(
        transaction_id,
        [
            {
                "dependency_name": action.dependency_name,
                "action_type": action.action_type,
                "command": list(action.command),
                "description": action.description,
                "eligible": (
                    decision_by_dependency[action.dependency_name].eligible
                ),
                "policy_reason": (
                    decision_by_dependency[action.dependency_name].reason
                ),
            }
            for action in remediation_plan
        ],
    )

    for action in remediation_plan:
        decision = decision_by_dependency[action.dependency_name]

        state.record(
            transaction_id,
            "remediation_policy",
            "eligible" if decision.eligible else "blocked",
            (
                f"{action.dependency_name}: "
                f"{decision.reason}"
            ),
        )

        state.record(
            transaction_id,
            "remediation_plan",
            "planned",
            (
                f"{action.dependency_name}: "
                f"{action.action_type} "
                f"{action.command!r}"
            ),
        )

    if not dry_run:
        for position, action in enumerate(remediation_plan):
            decision = decision_by_dependency[action.dependency_name]
            if not decision.eligible:
                continue
            state.record(
                transaction_id,
                "remediation_execution",
                "automatic",
                f"{action.dependency_name}: automatic remediation authorized",
            )
            try:
                execute_remediation_attempt(
                    state=state,
                    transaction_id=transaction_id,
                    position=position,
                    decision=decision,
                    manifest=manifest,
                    cwd=target_dir,
                )
            except Exception as exc:
                state.finish(
                    transaction_id,
                    status="remediation_failed",
                    stage="remediation_execution",
                    error_message=str(exc),
                )
                raise InstallError(
                    f"Automatic remediation failed for {action.dependency_name}: {exc}"
                ) from exc

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
    for position, check in enumerate(context.manifest.health_checks):
        try:
            result = execute_command(
                list(check.command),
                cwd=context.target_dir,
            )
        except CommandExecutionError as exc:
            result = exc.result
            context.state.record_health_check_result(
                context.transaction_id, name=check.name, position=position,
                status="failed", return_code=result.returncode,
                timed_out=result.timed_out, stdout=result.stdout, stderr=result.stderr,
            )
            raise
        context.state.record_health_check_result(
            context.transaction_id, name=check.name, position=position,
            status="success", return_code=result.returncode,
            timed_out=result.timed_out, stdout=result.stdout, stderr=result.stderr,
        )


def restart_declared_services(context: InstallContext) -> None:
    if not context.manifest.operations.restart_services:
        return
    for service in context.manifest.operations.services:
        name = service.name.strip()
        if not name or any(ch.isspace() for ch in name) or "/" in name:
            raise InstallError(f"Invalid service name: {service.name!r}")
        execute_command(["systemctl", "restart", name], cwd=context.target_dir)
        execute_command(["systemctl", "is-active", "--quiet", name], cwd=context.target_dir)
        context.state.record(context.transaction_id, "service_restart", "success", name)


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

        if context.manifest.operations.restart_services:
            context.state.heartbeat(context.transaction_id)
            context.state.record(context.transaction_id, "service_restart", "started")
            restart_declared_services(context)

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
