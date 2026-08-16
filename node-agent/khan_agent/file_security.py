from __future__ import annotations

import platform
import subprocess
from pathlib import Path


def secure_private_file(path: Path) -> None:
    """Restrict a private agent file to the current OS identity."""
    path = Path(path)

    if platform.system() != "Windows":
        path.chmod(0o600)
        return

    result = subprocess.run(
        [
            "icacls",
            str(path),
            "/inheritance:r",
            "/grant:r",
            "*S-1-5-18:(F)",
            "*S-1-5-32-544:(F)",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(
            "Unable to secure private file permissions"
            + (f": {detail}" if detail else "")
        )
