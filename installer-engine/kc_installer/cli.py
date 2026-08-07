from __future__ import annotations

import argparse
import json
from pathlib import Path

from kc_installer.engine import (
    RemediationExecutionError,
    execute_remediation_attempt,
    install,
    recover_transaction,
)
from kc_installer.manifest import load_manifest, validate_manifest_files
from kc_installer.paths import InstallerPaths
from kc_installer.preflight import (
    RemediationPolicyDecision,
    build_remediation_plan,
    classify_dependencies,
    run_preflight,
)
from kc_installer.state import InstallerState
from kc_installer.trust import verify_package_signature


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="kc-installer",
        description="Khan Cloud manifest-driven installer engine",
    )

    sub = root.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate")
    validate.add_argument("package")

    plan = sub.add_parser("plan")
    plan.add_argument("package")
    plan.add_argument(
        "--target",
        default="/opt/khan-cloud/source",
    )

    install_cmd = sub.add_parser("install")
    install_cmd.add_argument("package")
    install_cmd.add_argument(
        "--target",
        default="/opt/khan-cloud/source",
    )
    install_cmd.add_argument("--dry-run", action="store_true")

    history = sub.add_parser("history")
    history.add_argument("--limit", type=int, default=20)

    show = sub.add_parser("show")
    show.add_argument("transaction_id")

    remediate = sub.add_parser("remediate")
    remediate.add_argument("transaction_id")
    remediate.add_argument("position", type=int)
    remediate.add_argument(
        "--timeout-seconds",
        type=float,
        default=300.0,
    )

    recovery_status = sub.add_parser("recovery-status")
    recovery_status.add_argument(
        "--stale-after-seconds",
        type=int,
        default=300,
    )

    recover = sub.add_parser("recover")
    recover.add_argument("transaction_id")
    recover.add_argument(
        "--stale-after-seconds",
        type=int,
        default=300,
    )
    recover.add_argument(
        "--rollback",
        action="store_true",
        help="Restore the recorded pre-installation state.",
    )

    sub.add_parser("self-test")

    return root


def main() -> None:
    args = parser().parse_args()

    if args.command == "validate":
        package = Path(args.package).resolve()
        manifest = load_manifest(package)
        errors = validate_manifest_files(package, manifest)

        if errors:
            raise SystemExit("\n".join(errors))

        print(
            json.dumps(
                {
                    "status": "valid",
                    "feature_pack": manifest.feature_pack.model_dump(),
                },
                indent=2,
                default=str,
            )
        )
        return

    if args.command == "plan":
        package = Path(args.package).resolve()
        target = Path(args.target).resolve()

        manifest = load_manifest(package)
        errors = validate_manifest_files(package, manifest)

        if errors:
            raise SystemExit("\n".join(errors))

        preflight_results = run_preflight(manifest, target)
        dependency_results = classify_dependencies(manifest)
        remediation_plan = build_remediation_plan(manifest)

        print(
            json.dumps(
                {
                    "feature_pack": manifest.feature_pack.model_dump(),
                    "preflight": [
                        {
                            "name": item.name,
                            "passed": item.passed,
                            "actual": item.actual,
                            "required": item.required,
                        }
                        for item in preflight_results
                    ],
                    "dependencies": [
                        {
                            "name": item.name,
                            "classification": item.classification,
                            "available": item.available,
                            "command": item.command,
                            "description": item.description,
                        }
                        for item in dependency_results
                    ],
                    "remediation_plan": [
                        {
                            "dependency": item.dependency_name,
                            "type": item.action_type,
                            "command": item.command,
                            "description": item.description,
                        }
                        for item in remediation_plan
                    ],
                },
                indent=2,
                default=str,
            )
        )
        return

    if args.command == "install":
        report = install(
            Path(args.package),
            Path(args.target),
            dry_run=args.dry_run,
        )
        print(f"Installation report: {report}")
        return

    paths = InstallerPaths.from_environment()

    if args.command == "history":
        state = InstallerState(paths.database_path)

        print(
            json.dumps(
                state.installations(args.limit),
                indent=2,
                default=str,
            )
        )
        return

    if args.command == "show":
        state = InstallerState(paths.database_path)

        installation = state.installation(args.transaction_id)

        if installation is None:
            raise SystemExit(
                f"Transaction not found: {args.transaction_id}"
            )

        print(
            json.dumps(
                {
                    "installation": installation,
                    "journal": state.journal(args.transaction_id),
                "remediation_plan": state.remediation_plan(
                    args.transaction_id
                ),
                "remediation_attempts": state.remediation_attempts(
                    args.transaction_id
                ),
                },
                indent=2,
                default=str,
            )
        )
        return

    if args.command == "remediate":
        state = InstallerState(paths.database_path)

        installation = state.installation(args.transaction_id)

        if installation is None:
            raise SystemExit(
                f"Transaction not found: {args.transaction_id}"
            )

        actions = state.remediation_plan(args.transaction_id)

        action = next(
            (
                item
                for item in actions
                if item["position"] == args.position
            ),
            None,
        )

        if action is None:
            raise SystemExit(
                (
                    "Remediation action not found: "
                    f"transaction={args.transaction_id}, "
                    f"position={args.position}"
                )
            )

        if action["eligible"] is not True:
            raise SystemExit(
                (
                    "Remediation blocked: "
                    f"{action.get('policy_reason') or 'not eligible'}"
                )
            )

        package_path = Path(installation["package_path"])
        target_path = Path(installation["target_path"])

        manifest = load_manifest(package_path)
        trust_result = verify_package_signature(
            package_path,
            paths.trust_store_dir,
        )
        if (
            not trust_result.trusted
            or installation.get("package_trusted") != 1
            or trust_result.signer_id != installation.get("signer_id")
            or trust_result.package_digest != installation.get("package_digest")
        ):
            raise SystemExit(
                "Package trust no longer matches the persisted transaction; "
                "refusing remediation."
            )

        if (
            manifest.feature_pack.id
            != installation["feature_pack_id"]
            or manifest.feature_pack.version
            != installation["feature_pack_version"]
        ):
            raise SystemExit(
                "Stored transaction and package manifest no longer match."
            )

        dependency = next(
            (
                item
                for item in manifest.preflight.dependencies
                if item.name == action["dependency_name"]
            ),
            None,
        )

        if (
            dependency is None
            or dependency.classification != "remediable"
            or dependency.remediation is None
            or dependency.remediation.type != action["action_type"]
            or list(dependency.remediation.command)
            != list(action["command"])
        ):
            raise SystemExit(
                (
                    "Persisted remediation plan and package manifest "
                    "no longer match; refusing execution."
                )
            )

        decision = RemediationPolicyDecision(
            dependency_name=action["dependency_name"],
            action_type=action["action_type"],
            command=list(action["command"]),
            description=action["description"],
            eligible=True,
            reason=action.get("policy_reason") or "eligible",
        )

        try:
            result = execute_remediation_attempt(
                state=state,
                transaction_id=args.transaction_id,
                position=args.position,
                decision=decision,
                manifest=manifest,
                cwd=target_path,
                timeout_seconds=args.timeout_seconds,
            )
        except RemediationExecutionError as exc:
            attempts = [
                item
                for item in state.remediation_attempts(
                    args.transaction_id
                )
                if item["position"] == args.position
            ]

            output = {
                "transaction_id": args.transaction_id,
                "position": args.position,
                "dependency_name": action["dependency_name"],
                "status": (
                    attempts[-1]["status"]
                    if attempts
                    else "failed"
                ),
                "verified": False,
                "error": str(exc),
                "attempt": attempts[-1] if attempts else None,
            }

            print(
                json.dumps(
                    output,
                    indent=2,
                    default=str,
                )
            )

            raise SystemExit(1) from exc

        attempts = [
            item
            for item in state.remediation_attempts(
                args.transaction_id
            )
            if item["position"] == args.position
        ]

        print(
            json.dumps(
                {
                    "transaction_id": args.transaction_id,
                    "position": args.position,
                    "dependency_name": result.dependency_name,
                    "status": "success",
                    "verified": result.verified,
                    "attempt": attempts[-1],
                },
                indent=2,
                default=str,
            )
        )
        return

    if args.command == "recovery-status":
        state = InstallerState(paths.database_path)

        result = state.classify_incomplete(
            stale_after_seconds=args.stale_after_seconds,
        )

        print(
            json.dumps(
                result,
                indent=2,
                default=str,
            )
        )
        return

    if args.command == "recover":
        state = InstallerState(paths.database_path)

        matches = [
            item
            for item in state.classify_incomplete(
                stale_after_seconds=args.stale_after_seconds,
            )
            if item["transaction_id"] == args.transaction_id
        ]

        if not matches:
            raise SystemExit(
                "Transaction is not currently incomplete or was not found."
            )

        item = matches[0]

        if item["classification"] == "active":
            raise SystemExit(
                "Recovery refused: transaction is still active."
            )

        if item["classification"] not in {
            "interrupted",
            "stale",
        }:
            raise SystemExit(
                "Recovery refused: transaction is not safely recoverable."
            )

        if args.rollback:
            try:
                result = recover_transaction(
                    args.transaction_id,
                    stale_after_seconds=args.stale_after_seconds,
                    paths=paths,
                )
            except Exception as exc:
                raise SystemExit(str(exc)) from exc

            print(
                json.dumps(
                    result,
                    indent=2,
                    default=str,
                )
            )
            return

        state.mark_recovery_requested(args.transaction_id)

        print(
            json.dumps(
                {
                    "status": "recovery_requested",
                    "transaction_id": args.transaction_id,
                    "classification": item["classification"],
                    "current_stage": item["current_stage"],
                    "backup_path": item["backup_path"],
                },
                indent=2,
                default=str,
            )
        )
        return

    if args.command == "self-test":
        print(
            json.dumps(
                {
                    "status": "healthy",
                    "component": "installer-engine",
                    "version": "0.9.1",
                }
            )
        )
