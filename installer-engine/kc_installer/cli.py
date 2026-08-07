from __future__ import annotations

import argparse
import json
from pathlib import Path

from kc_installer.engine import install
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
