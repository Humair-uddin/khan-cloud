from __future__ import annotations

from pathlib import Path

import yaml

from kc_installer.models import Manifest


class ManifestError(ValueError):
    pass


def load_manifest(package_dir: Path) -> Manifest:
    path = package_dir / "manifest.yaml"
    if not path.exists():
        raise ManifestError("manifest.yaml is missing.")

    raw = yaml.safe_load(path.read_text()) or {}
    return Manifest.model_validate(raw)


def validate_manifest_files(package_dir: Path, manifest: Manifest) -> list[str]:
    errors: list[str] = []

    for name, component in manifest.components.items():
        if not component.enabled:
            continue
        if component.source is None:
            errors.append(f"Component {name!r} is enabled but has no source.")
            continue
        source = package_dir / component.source
        if not source.exists():
            errors.append(
                f"Component {name!r} references missing source: {source}"
            )
        if component.destination is None:
            errors.append(
                f"Component {name!r} is enabled but has no destination."
            )

    return errors
