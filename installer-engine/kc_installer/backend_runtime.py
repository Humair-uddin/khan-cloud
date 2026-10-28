from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path


class BackendRuntimeError(RuntimeError):
    """Backend runtime preparation or activation failed."""


@dataclass(frozen=True)
class RuntimeCandidate:
    path: Path
    requirements_sha256: str


def _run(command: list[str], *, timeout: int = 900) -> None:
    try:
        subprocess.run(
            command,
            check=True,
            timeout=timeout,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise BackendRuntimeError(
            f"Runtime command failed: {command[0]}"
        ) from exc


def _validate_runtime_root(runtime_root: Path) -> Path:
    root = runtime_root.resolve(strict=True)

    if not root.is_dir():
        raise BackendRuntimeError("Runtime root is not a directory.")

    return root


def _validate_candidate(root: Path, candidate: Path) -> Path:
    candidate = candidate.resolve(strict=True)

    if candidate.parent != root:
        raise BackendRuntimeError(
            "Candidate must be a direct child of runtime root."
        )

    if not candidate.is_dir():
        raise BackendRuntimeError("Candidate is not a directory.")

    python = candidate / "bin" / "python"

    if not python.is_file():
        raise BackendRuntimeError(
            "Candidate Python interpreter is missing."
        )

    return candidate


def prepare_backend_runtime(
    *,
    runtime_root: Path,
    requirements: Path,
    python_executable: Path | None = None,
) -> RuntimeCandidate:
    root = _validate_runtime_root(runtime_root)

    requirements = requirements.resolve(strict=True)

    if not requirements.is_file():
        raise BackendRuntimeError(
            "Requirements path must reference a file."
        )

    digest = hashlib.sha256(requirements.read_bytes()).hexdigest()

    name = f"backend-{digest[:16]}-{uuid.uuid4().hex[:12]}"
    candidate = root / name

    interpreter = (
        python_executable.resolve(strict=True)
        if python_executable is not None
        else Path(sys.executable).resolve(strict=True)
    )

    if not interpreter.is_file():
        raise BackendRuntimeError(
            "Python interpreter is unavailable."
        )

    try:
        _run([
            str(interpreter),
            "-m",
            "venv",
            str(candidate),
        ])

        python = candidate / "bin" / "python"

        _run([
            str(python),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "-r",
            str(requirements),
        ])

        _run([
            str(python),
            "-m",
            "pip",
            "check",
        ])

        _validate_candidate(root, candidate)

    except Exception:
        # Do not automatically delete an incompletely built environment:
        # preserve it for diagnosis until transaction cleanup is integrated.
        raise

    return RuntimeCandidate(
        path=candidate,
        requirements_sha256=digest,
    )


def activate_backend_runtime(
    *,
    runtime_root: Path,
    active_link: Path,
    candidate: Path,
) -> Path | None:
    root = _validate_runtime_root(runtime_root)
    candidate = _validate_candidate(root, candidate)

    active_link = Path(os.path.abspath(active_link))

    if active_link.is_symlink():
        previous = active_link.resolve(strict=True)
        _validate_candidate(root, previous)
    elif active_link.exists():
        raise BackendRuntimeError(
            "Active runtime path is not a managed symlink."
        )
    else:
        previous = None

    active_link.parent.mkdir(parents=True, exist_ok=True)

    temporary_link = active_link.with_name(
        f".{active_link.name}.next-{uuid.uuid4().hex}"
    )

    try:
        temporary_link.symlink_to(candidate, target_is_directory=True)
        os.replace(temporary_link, active_link)
    finally:
        temporary_link.unlink(missing_ok=True)

    return previous


def restore_backend_runtime(
    *,
    runtime_root: Path,
    active_link: Path,
    previous: Path | None,
) -> None:
    root = _validate_runtime_root(runtime_root)
    active_link = Path(os.path.abspath(active_link))

    if not active_link.is_symlink():
        raise BackendRuntimeError(
            "Rollback requires a managed active symlink."
        )

    if previous is None:
        active_link.unlink()
        return

    previous = _validate_candidate(root, previous)

    temporary_link = active_link.with_name(
        f".{active_link.name}.restore-{uuid.uuid4().hex}"
    )

    try:
        temporary_link.symlink_to(
            previous,
            target_is_directory=True,
        )
        os.replace(temporary_link, active_link)
    finally:
        temporary_link.unlink(missing_ok=True)
