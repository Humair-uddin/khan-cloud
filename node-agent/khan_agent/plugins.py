from __future__ import annotations

import importlib.util
import logging
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Protocol

logger = logging.getLogger(__name__)


class AgentPlugin(Protocol):
    name: str
    version: str

    def health(self) -> dict[str, object]: ...


@dataclass
class LoadedPlugin:
    name: str
    version: str
    instance: AgentPlugin


class PluginManager:
    """Loads opt-in plugins from the configured directory.

    Plugins are observational in this release. No plugin receives an execution
    channel for destructive or system-changing actions.
    """

    def __init__(self, plugin_directory: Path) -> None:
        self.plugin_directory = plugin_directory
        self.plugins: list[LoadedPlugin] = []

    def load_all(self) -> list[LoadedPlugin]:
        if not self.plugin_directory.exists():
            return []

        for path in sorted(self.plugin_directory.glob("*.py")):
            plugin = self._load(path)
            if plugin is not None:
                self.plugins.append(plugin)
        return list(self.plugins)

    def _load(self, path: Path) -> LoadedPlugin | None:
        spec = importlib.util.spec_from_file_location(f"khan_plugin_{path.stem}", path)
        if spec is None or spec.loader is None:
            logger.warning("plugin_spec_failed", extra={"plugin_path": str(path)})
            return None

        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
            instance = self._create_instance(module)
            return LoadedPlugin(
                name=str(instance.name),
                version=str(instance.version),
                instance=instance,
            )
        except Exception:
            logger.exception("plugin_load_failed", extra={"plugin_path": str(path)})
            return None

    @staticmethod
    def _create_instance(module: ModuleType) -> AgentPlugin:
        factory = getattr(module, "create_plugin", None)
        if factory is None:
            raise ValueError("plugin must expose create_plugin()")
        instance = factory()
        if not hasattr(instance, "name") or not hasattr(instance, "version"):
            raise ValueError("plugin is missing name/version")
        return instance
