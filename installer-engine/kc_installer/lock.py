from __future__ import annotations

import fcntl
from pathlib import Path
from typing import TextIO


class InstallerLockError(RuntimeError):
    pass


class InstallerLock:
    def __init__(self, lock_path: Path) -> None:
        self.lock_path = lock_path
        self._handle: TextIO | None = None

    def acquire(self) -> None:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self.lock_path.open("a+")

        try:
            fcntl.flock(
                self._handle.fileno(),
                fcntl.LOCK_EX | fcntl.LOCK_NB,
            )
        except BlockingIOError as exc:
            self._handle.close()
            self._handle = None
            raise InstallerLockError(
                "Another Khan Cloud installation is already running."
            ) from exc

    def release(self) -> None:
        if self._handle is None:
            return

        fcntl.flock(
            self._handle.fileno(),
            fcntl.LOCK_UN,
        )
        self._handle.close()
        self._handle = None

    def __enter__(self) -> "InstallerLock":
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.release()
