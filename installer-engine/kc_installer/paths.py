from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class InstallerPaths:
    source_root: Path
    platform_root: Path
    runtime_root: Path
    state_root: Path
    backup_root: Path
    package_root: Path

    @classmethod
    def from_environment(cls) -> "InstallerPaths":
        platform_root = Path(
            os.environ.get("KHAN_CLOUD_ROOT", "/opt/khan-cloud")
        ).resolve()

        source_root = Path(
            os.environ.get(
                "KHAN_CLOUD_SOURCE_ROOT",
                str(platform_root / "source"),
            )
        ).resolve()

        runtime_root = Path(
            os.environ.get(
                "KHAN_CLOUD_INSTALLER_RUNTIME",
                str(platform_root / "runtime" / "installer"),
            )
        ).resolve()

        state_root = Path(
            os.environ.get(
                "KHAN_CLOUD_INSTALLER_STATE",
                str(platform_root / "state" / "installer"),
            )
        ).resolve()

        backup_root = Path(
            os.environ.get(
                "KHAN_CLOUD_BACKUP_ROOT",
                str(platform_root / "backups" / "feature-packs"),
            )
        ).resolve()

        package_root = Path(
            os.environ.get(
                "KHAN_CLOUD_PACKAGE_ROOT",
                str(platform_root / "packages"),
            )
        ).resolve()

        return cls(
            source_root=source_root,
            platform_root=platform_root,
            runtime_root=runtime_root,
            state_root=state_root,
            backup_root=backup_root,
            package_root=package_root,
        )

    @property
    def reports_dir(self) -> Path:
        return self.runtime_root / "reports"

    @property
    def logs_dir(self) -> Path:
        return self.runtime_root / "logs"

    @property
    def cache_dir(self) -> Path:
        return self.runtime_root / "cache"

    @property
    def temp_dir(self) -> Path:
        return self.runtime_root / "temp"

    @property
    def venv_dir(self) -> Path:
        return self.runtime_root / ".venv"

    @property
    def history_dir(self) -> Path:
        return self.state_root / "history"

    @property
    def checkpoint_dir(self) -> Path:
        return self.state_root / "checkpoints"

    @property
    def lock_dir(self) -> Path:
        return self.state_root / "locks"

    @property
    def database_path(self) -> Path:
        return self.state_root / "installer.db"

    def ensure_directories(self) -> None:
        directories = (
            self.runtime_root,
            self.reports_dir,
            self.logs_dir,
            self.cache_dir,
            self.temp_dir,
            self.state_root,
            self.history_dir,
            self.checkpoint_dir,
            self.lock_dir,
            self.backup_root,
            self.package_root,
        )

        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
