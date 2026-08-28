#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
import xml.etree.ElementTree as ET


REQUIRED_DRIVER_FILES = (
    "KhanVirtualDisplay.inf",
    "KhanVirtualDisplay.dll",
    "KhanVirtualDisplay.cat",
)

REQUIRED_RUNTIME_FILES = (
    "RuntimeConfig/khan-vdd-settings.xml",
    "RuntimeConfig/EDID/monitor_profile.xml",
)


class PackageError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def validate_runtime_config(settings: Path) -> dict:
    try:
        root = ET.parse(settings).getroot()
    except (ET.ParseError, OSError) as exc:
        raise PackageError(f"invalid runtime settings XML: {exc}") from exc

    resolutions = root.findall(".//resolution")
    if not resolutions:
        raise PackageError(
            "runtime settings contains no <resolution> entries"
        )

    modes = []
    seen = set()

    for node in resolutions:
        def value(name: str):
            attr = node.get(name)
            if attr is not None:
                return attr

            child = node.find(name)
            if child is not None and child.text:
                return child.text.strip()

            return None

        width = value("width")
        height = value("height")
        refresh = (
            value("refresh_rate")
            or value("refresh")
            or value("hz")
        )

        if width is None or height is None or refresh is None:
            raise PackageError(
                "runtime resolution entry missing width/height/refresh"
            )

        try:
            mode = (int(width), int(height), int(refresh))
        except ValueError as exc:
            raise PackageError(
                "runtime resolution contains non-integer values"
            ) from exc

        if mode in seen:
            raise PackageError(
                f"duplicate runtime mode: {mode[0]}x{mode[1]}@{mode[2]}"
            )

        seen.add(mode)
        modes.append(mode)

    return {
        "mode_count": len(modes),
        "modes": [
            {
                "width": w,
                "height": h,
                "refresh_hz": r,
            }
            for w, h, r in modes
        ],
    }


def locate_required_files(build_dir: Path) -> dict[str, Path]:
    files = {}

    for name in REQUIRED_DRIVER_FILES:
        path = build_dir / name
        if not path.is_file():
            raise PackageError(f"required driver artifact missing: {path}")
        files[name] = path

    for relative in REQUIRED_RUNTIME_FILES:
        path = build_dir / Path(relative)
        if not path.is_file():
            raise PackageError(f"required runtime artifact missing: {path}")
        files[relative] = path

    return files


def write_package(build_dir: Path, output: Path) -> dict:
    build_dir = build_dir.resolve()
    output = output.resolve()

    if not build_dir.is_dir():
        raise PackageError(f"build directory does not exist: {build_dir}")

    files = locate_required_files(build_dir)

    runtime = validate_runtime_config(
        files["RuntimeConfig/khan-vdd-settings.xml"]
    )

    manifest = {
        "schema": "khan-cloud-vdd-package-v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "runtime_config_required": True,
        "runtime_mode_count": runtime["mode_count"],
        "runtime_modes": runtime["modes"],
        "files": {},
    }

    for relative, path in sorted(files.items()):
        manifest["files"][relative] = {
            "sha256": sha256(path),
            "bytes": path.stat().st_size,
        }

    output.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(
        prefix="khan-vdd-package-"
    ) as temporary:
        stage = Path(temporary) / "KhanVirtualDisplay"
        stage.mkdir(parents=True)

        for relative, source in files.items():
            destination = stage / Path(relative)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)

        manifest_path = stage / "package-manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        temporary_zip = output.with_suffix(output.suffix + ".new")
        temporary_zip.unlink(missing_ok=True)

        with zipfile.ZipFile(
            temporary_zip,
            "w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=9,
        ) as archive:
            for path in sorted(stage.rglob("*")):
                if path.is_file():
                    archive.write(
                        path,
                        path.relative_to(stage.parent).as_posix(),
                    )

        temporary_zip.replace(output)

    with zipfile.ZipFile(output, "r") as archive:
        names = set(archive.namelist())

    required_zip_entries = {
        "KhanVirtualDisplay/KhanVirtualDisplay.inf",
        "KhanVirtualDisplay/KhanVirtualDisplay.dll",
        "KhanVirtualDisplay/KhanVirtualDisplay.cat",
        "KhanVirtualDisplay/RuntimeConfig/khan-vdd-settings.xml",
        "KhanVirtualDisplay/RuntimeConfig/EDID/monitor_profile.xml",
        "KhanVirtualDisplay/package-manifest.json",
    }

    missing = sorted(required_zip_entries - names)
    if missing:
        output.unlink(missing_ok=True)
        raise PackageError(
            "package self-validation failed; missing: " + ", ".join(missing)
        )

    manifest["package_sha256"] = sha256(output)
    manifest["package_bytes"] = output.stat().st_size

    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a self-validating Khan Virtual Display package."
    )
    parser.add_argument(
        "--build-dir",
        required=True,
        type=Path,
        help="KhanVirtualDisplay build output directory",
    )
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="output ZIP path",
    )
    args = parser.parse_args()

    try:
        result = write_package(args.build_dir, args.output)
    except PackageError as exc:
        print(f"PACKAGE_GATE=FAIL")
        print(f"ERROR={exc}")
        return 1

    print("PACKAGE_GATE=PASS")
    print(f"PACKAGE={args.output.resolve()}")
    print(f"PACKAGE_SHA256={result['package_sha256']}")
    print(f"PACKAGE_BYTES={result['package_bytes']}")
    print(f"RUNTIME_MODE_COUNT={result['runtime_mode_count']}")

    for mode in result["runtime_modes"]:
        print(
            "RUNTIME_MODE="
            f"{mode['width']}x{mode['height']}@{mode['refresh_hz']}"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
