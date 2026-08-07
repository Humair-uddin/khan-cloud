from pathlib import Path

import pytest

from kc_installer.lock import InstallerLock, InstallerLockError


def test_lock_can_be_acquired_and_released(tmp_path: Path) -> None:
    lock_path = tmp_path / "installer.lock"

    with InstallerLock(lock_path):
        assert lock_path.exists()

    with InstallerLock(lock_path):
        assert lock_path.exists()


def test_second_lock_is_rejected(tmp_path: Path) -> None:
    lock_path = tmp_path / "installer.lock"

    first = InstallerLock(lock_path)
    second = InstallerLock(lock_path)

    first.acquire()

    try:
        with pytest.raises(InstallerLockError):
            second.acquire()
    finally:
        first.release()
