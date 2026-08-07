from __future__ import annotations

import argparse
import json
from pathlib import Path

from kc_installer.engine import install, recover_transaction
from kc_installer.manifest import load_manifest, validate_manifest_files
from kc_installer.paths import InstallerPaths
from kc_installer.state import InstallerState


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="kc-installer",
        description="Khan Cloud manifest-driven installer engine",
    )

    sub = root.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate")
    validate.add_argument("package")

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
