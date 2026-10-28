from __future__ import annotations

from pathlib import Path


class ProtectedDestinationError(ValueError):
    """A component destination overlaps protected backend state."""


PROTECTED_BACKEND_PATHS = (
    Path("backend/.venv"),
    Path("backend/.env"),
)


def validate_component_destination(
    target_root: Path,
    destination: Path,
) -> Path:
    root = target_root.resolve(strict=True)

    relative = Path(destination)

    if relative.is_absolute() or ".." in relative.parts:
        raise ProtectedDestinationError(
            "Component destination must be relative and contained."
        )

    candidate = root / relative

    # Reject symlink traversal through any existing path component.
    cursor = root
    for part in relative.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ProtectedDestinationError(
                f"Symlink destination path refused: {cursor}"
            )

    resolved = candidate.resolve(strict=False)

    try:
        normalized = resolved.relative_to(root)
    except ValueError as exc:
        raise ProtectedDestinationError(
            "Component destination escapes target root."
        ) from exc

    for protected in PROTECTED_BACKEND_PATHS:
        if (
            normalized == protected
            or normalized in protected.parents
            or protected in normalized.parents
        ):
            raise ProtectedDestinationError(
                f"Component destination overlaps protected path: "
                f"{protected}"
            )

    return resolved
