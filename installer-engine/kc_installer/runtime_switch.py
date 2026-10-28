from __future__ import annotations

import os
import uuid
from pathlib import Path

from kc_installer.backend_runtime import (
    BackendRuntimeError,
    _validate_candidate,
    _validate_runtime_root,
)


def _sync_directory(directory: Path) -> None:
    descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def current_runtime(root: Path, link: Path) -> Path | None:
    root = _validate_runtime_root(root)
    link = Path(os.path.abspath(link))

    if link.is_symlink():
        return _validate_candidate(root, link.resolve(strict=True))

    if os.path.lexists(link):
        raise BackendRuntimeError("Active runtime is not a symlink.")

    return None


def switch_runtime(
    *,
    runtime_root: Path,
    active_link: Path,
    expected: Path | None,
    replacement: Path | None,
) -> None:
    root = _validate_runtime_root(runtime_root)
    link = Path(os.path.abspath(active_link))

    observed = current_runtime(root, link)
    wanted = (
        _validate_candidate(root, expected)
        if expected is not None
        else None
    )

    if observed != wanted:
        raise BackendRuntimeError(
            "Runtime ownership conflict: active generation changed."
        )

    target = (
        _validate_candidate(root, replacement)
        if replacement is not None
        else None
    )

    if target is None:
        if observed is not None:
            link.unlink()
            _sync_directory(link.parent)
        return

    link.parent.mkdir(parents=True, exist_ok=True)

    temporary = link.with_name(
        f".{link.name}.switch-{uuid.uuid4().hex}"
    )

    try:
        temporary.symlink_to(target, target_is_directory=True)
        _sync_directory(link.parent)
        os.replace(temporary, link)
        _sync_directory(link.parent)
    finally:
        temporary.unlink(missing_ok=True)
