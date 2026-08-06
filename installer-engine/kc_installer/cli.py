from __future__ import annotations

import argparse
import json
from pathlib import Path

from kc_installer.engine import install
from kc_installer.manifest import load_manifest, validate_manifest_files


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
    install_cmd.add_argument("--target", default="/opt/khan-cloud/source")
    install_cmd.add_argument("--dry-run", action="store_true")

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

    if args.command == "self-test":
        print(
            json.dumps(
                {
                    "status": "healthy",
                    "component": "installer-engine",
                    "version": "0.9.0",
                }
            )
        )
