from __future__ import annotations

import asyncio
import json
import logging
import signal
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from khan_agent import __version__
from khan_agent.client import ControlPlaneClient
from khan_agent.config import AgentSettings
from khan_agent.identity import IdentityStore
from khan_agent.plugins import PluginManager
from khan_agent.state import AgentState, StateMachine

logger = logging.getLogger("khan_agent")


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


class AgentRuntime:
    def __init__(self, settings: AgentSettings) -> None:
        self.settings = settings
        self.state = StateMachine()
        self.stop_event = asyncio.Event()
        self.identity = IdentityStore(
            settings.agent.state_directory
        ).load_or_create()
        self.client = ControlPlaneClient(settings)
        self.plugin_manager = PluginManager(settings.agent.plugin_directory)

    async def run(self, once: bool = False) -> None:
        configure_logging(self.settings.agent.log_level)
        self._install_signal_handlers()
        self.state.transition(AgentState.CONFIGURED)
        plugins = self.plugin_manager.load_all()

        startup = {
            "event": "agent_started",
            "version": __version__,
            "state": self.state.current,
            "identity": asdict(self.identity),
            "observation_only": self.settings.agent.observation_only,
            "plugins": [{"name": p.name, "version": p.version} for p in plugins],
        }
        logger.info(json.dumps(startup, default=str))

        if once or not self.settings.heartbeat.enabled:
            logger.info(
                json.dumps(
                    {
                        "event": "agent_check_complete",
                        "heartbeat_enabled": self.settings.heartbeat.enabled,
                        "message": "No system changes were made.",
                    }
                )
            )
            self.state.transition(AgentState.STOPPED)
            return

        await self._heartbeat_loop()
        self.state.transition(AgentState.STOPPED)

    async def _heartbeat_loop(self) -> None:
        while not self.stop_event.is_set():
            self.state.transition(AgentState.CONNECTING)
            try:
                payload = {
                    "node_uuid": self.identity.node_uuid,
                    "node_name": self.settings.agent.node_name,
                    "agent_version": __version__,
                    "agent_state": self.state.current,
                    "timestamp": datetime.now(UTC).isoformat(),
                    "observation_only": self.settings.agent.observation_only,
                }
                await self.client.heartbeat(payload)
                self.state.transition(AgentState.CONNECTED)
                logger.info(
                    json.dumps(
                        {
                            "event": "heartbeat_success",
                            "node_uuid": self.identity.node_uuid,
                        }
                    )
                )
            except Exception as exc:
                self.state.transition(AgentState.DISCONNECTED)
                logger.warning(
                    json.dumps(
                        {
                            "event": "heartbeat_failed",
                            "node_uuid": self.identity.node_uuid,
                            "error": str(exc),
                        }
                    )
                )

            try:
                await asyncio.wait_for(
                    self.stop_event.wait(),
                    timeout=self.settings.agent.heartbeat_interval_seconds,
                )
            except TimeoutError:
                pass

    def _install_signal_handlers(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, self.stop_event.set)
            except NotImplementedError:
                # Windows event loops may not support signal handlers.
                pass
