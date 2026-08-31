from __future__ import annotations

import asyncio
import json
import logging
import platform
import signal
from dataclasses import asdict

from khan_agent import __version__
from khan_agent.client import ControlPlaneClient
from khan_agent.config import AgentSettings
from khan_agent.credentials import CredentialStore, NodeCredentials
from khan_agent.identity import IdentityStore
from khan_agent.inventory import collect_safe_inventory
from khan_agent.installer_telemetry import read_latest_installer_snapshot
from khan_agent.plugins import PluginManager
from khan_agent.job_dispatch import execute_node_job
from khan_agent.job_result_spool import JobResultSpool
from khan_agent.state import AgentState, StateMachine
from khan_agent.provisioning import ProvisioningStateStore
from khan_agent.windows_image_builder import WindowsGoldenImageBuilder, WindowsImageBuildPlan

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
        self._event_loop: asyncio.AbstractEventLoop | None = None
        self.identity = IdentityStore(
            settings.agent.state_directory
        ).load_or_create()
        self.credential_store = CredentialStore(settings.agent.state_directory)
        self.client = ControlPlaneClient(settings)
        self.plugin_manager = PluginManager(settings.agent.plugin_directory)
        self._last_installer_telemetry_key: tuple[str, str, str] | None = None
        self.provisioning_store = ProvisioningStateStore(settings.agent.state_directory)
        self._last_provisioning_key: tuple[object, ...] | None = None
        self._desired_image_build_plan: dict[str, object] = {}
        self.job_result_spool = JobResultSpool(
            settings.agent.state_directory / "node-job-results"
        )

    def _inventory_payload(self) -> dict[str, object]:
        inventory = collect_safe_inventory()
        inventory.setdefault("virtualization", {})["execution_enabled"] = (
            self.settings.virtualization.execution_enabled
        )
        return inventory

    def _registration_payload(self) -> dict[str, object]:
        return {
            "name": self.settings.agent.node_name,
            "machine_id": self.identity.node_uuid,
            "hardware_identity": {
                "fingerprint": self.identity.hardware_fingerprint,
                "system_uuid": self.identity.system_uuid,
                "serial_number": self.identity.serial_number,
                "manufacturer": self.identity.manufacturer,
                "model": self.identity.model,
            },
            "hostname": self.identity.hostname,
            "operating_system": self.identity.platform,
            "kernel_version": self.identity.platform_release,
            "agent_version": __version__,
            "management_ip": "",
            "production_ip": "",
            "inventory": self._inventory_payload(),
        }

    def _heartbeat_payload(self) -> dict[str, object]:
        payload = self._registration_payload()
        payload.pop("name")
        payload.pop("machine_id")
        return payload

    async def enroll_once(self) -> None:
        configure_logging(self.settings.agent.log_level)

        if self.credential_store.exists():
            credentials = self.credential_store.load()
            logger.info(
                json.dumps(
                    {
                        "event": "enrollment_skipped",
                        "reason": "credentials_already_exist",
                        "node_id": credentials.node_id,
                    }
                )
            )
            return

        response = await self.client.enroll(self._registration_payload())
        credentials = NodeCredentials(
            node_id=str(response["node_id"]),
            node_secret=str(response["node_secret"]),
        )
        self.credential_store.save(credentials)

        logger.info(
            json.dumps(
                {
                    "event": "enrollment_success",
                    "node_id": credentials.node_id,
                    "status": response.get("status"),
                    "deployment_profile_id": response.get(
                        "deployment_profile_id"
                    ),
                    "intended_purpose": response.get("intended_purpose"),
                    "credentials_file": str(self.credential_store.path),
                }
            )
        )

    async def _report_installer_telemetry(self, credentials: NodeCredentials) -> None:
        if not self.settings.telemetry.enabled:
            return

        snapshot = read_latest_installer_snapshot(
            self.settings.telemetry.installer_database_path
        )
        if snapshot is None:
            return

        key = (snapshot.transaction_id, snapshot.status, snapshot.stage)
        if key == self._last_installer_telemetry_key:
            return

        try:
            await self.client.report_installation_event(
                snapshot.as_payload(),
                credentials,
            )
        except Exception as exc:
            logger.warning(
                json.dumps(
                    {
                        "event": "installer_telemetry_failed",
                        "transaction_id": snapshot.transaction_id,
                        "error": str(exc),
                    }
                )
            )
            return

        self._last_installer_telemetry_key = key

        logger.info(
            json.dumps(
                {
                    "event": "installer_telemetry_reported",
                    "transaction_id": snapshot.transaction_id,
                    "status": snapshot.status,
                    "stage": snapshot.stage,
                }
            )
        )

    async def _report_provisioning_state(self, credentials: NodeCredentials) -> None:
        if not self.settings.provisioning.enabled:
            return
        state = self.provisioning_store.load()
        payload = state.as_payload()
        key = (
            payload.get("deployment_id"), payload.get("stage"), payload.get("status"),
            payload.get("downloaded_bytes"), payload.get("total_bytes"),
            payload.get("last_checkpoint"), payload.get("retry_count"),
        )
        if key == self._last_provisioning_key:
            return
        reporter = getattr(self.client, "report_provisioning_event", None)
        if reporter is None:
            return
        await reporter(payload, credentials)
        self._last_provisioning_key = key

    async def _sync_desired_state(self, credentials: NodeCredentials) -> None:
        if not self.settings.provisioning.enabled:
            return
        getter = getattr(self.client, "desired_state", None)
        if getter is None:
            return
        desired = await getter(credentials)
        state = self.provisioning_store.load()
        wanted = str(desired.get("desired_image_version") or "")
        if wanted and state.desired_image_version != wanted:
            state.desired_image_version = wanted
            state.message = "Desired image version received from control plane."
            self.provisioning_store.save(state)
        self._desired_image_build_plan = dict(desired.get("image_build_plan") or {})

    async def _run_desired_image_build(self) -> None:
        if not self.settings.provisioning.image_builder_enabled or not self._desired_image_build_plan:
            return
        plan = WindowsImageBuildPlan.from_dict(self._desired_image_build_plan)
        state = self.provisioning_store.load()
        if state.desired_image_version == plan.image_version and state.last_checkpoint == "golden_vhdx_ready":
            return
        builder = WindowsGoldenImageBuilder(
            self.provisioning_store,
            worker_script=self.settings.provisioning.image_builder_worker_script,
        )
        await asyncio.to_thread(builder.build, plan)

    async def _flush_job_result_spool(
        self,
        credentials: NodeCredentials,
    ) -> bool:
        reporter = getattr(self.client, "report_job_result", None)
        if reporter is None:
            return False

        for entry in self.job_result_spool.pending():
            try:
                await reporter(entry.job_id, entry.payload, credentials)
            except Exception as exc:
                logger.warning(
                    json.dumps(
                        {
                            "event": "node_job_result_retry_deferred",
                            "job_id": entry.job_id,
                            "error": str(exc),
                        }
                    )
                )
                return False
            self.job_result_spool.remove(entry.job_id)
            logger.info(
                json.dumps(
                    {
                        "event": "node_job_result_recovered",
                        "job_id": entry.job_id,
                    }
                )
            )
        return True

    async def _process_one_node_job(self, credentials: NodeCredentials) -> None:
        next_job = getattr(self.client, "next_job", None)
        if next_job is None:
            return

        if not await self._flush_job_result_spool(credentials):
            return

        job = await next_job(credentials)
        if not job:
            return
        try:
            result = execute_node_job(
                job,
                virtualization_execution_enabled=(
                    self.settings.virtualization.execution_enabled
                ),
                virtualization_storage_root=(
                    self.settings.virtualization.storage_root
                ),
                virtualization_base_image_path=(
                    self.settings.virtualization.base_image_path
                ),
                virtualization_network_name=(
                    self.settings.virtualization.network_name
                ),
                gaming_execution_enabled=self.settings.gaming.enabled,
                gaming_execution_backend=(
                    self.settings.gaming.execution_backend
                ),
                gaming_streaming_backend=(
                    self.settings.gaming.streaming_backend
                ),
                gaming_state_root=(
                    self.settings.agent.state_directory / "gaming"
                ),
                gaming_sunshine_api_url=(
                    self.settings.gaming.sunshine_api_url
                ),
                gaming_sunshine_api_username=(
                    self.settings.gaming.sunshine_api_username
                ),
                gaming_sunshine_api_password=(
                    self.settings.gaming.sunshine_api_password
                ),
                gaming_sunshine_verify_tls=(
                    self.settings.gaming.sunshine_verify_tls
                ),
                gaming_vdd_template_path=(
                    self.settings.gaming.vdd_template_path
                ),
                gaming_vdd_target_root=(
                    self.settings.gaming.vdd_target_root
                ),
            )
        except Exception:  # defensive boundary around workload executors
            logger.exception(
                "Unexpected node job executor failure for job %s",
                job.get("id"),
            )
            from khan_agent.virtualization import JobExecutionResult

            result = JobExecutionResult(
                "failed",
                {},
                "Node job execution failed unexpectedly.",
            )
        result_payload = {
            "status": result.status,
            "result": result.result,
            "error_message": result.error_message,
        }
        job_id = str(job["id"])
        self.job_result_spool.save(job_id, result_payload)

        try:
            await self.client.report_job_result(
                job_id,
                result_payload,
                credentials,
            )
        except Exception as exc:
            logger.warning(
                json.dumps(
                    {
                        "event": "node_job_result_spooled",
                        "job_id": job_id,
                        "job_type": job.get("job_type"),
                        "status": result.status,
                        "error": str(exc),
                    }
                )
            )
            return

        self.job_result_spool.remove(job_id)
        logger.info(json.dumps({
            "event": "node_job_completed",
            "job_id": job_id,
            "job_type": job.get("job_type"),
            "status": result.status,
        }))

    async def heartbeat_once(self) -> None:
        configure_logging(self.settings.agent.log_level)

        if not self.credential_store.exists():
            raise RuntimeError(
                "Node is not enrolled. Run the agent with --enroll first."
            )

        credentials = self.credential_store.load()
        response = await self.client.heartbeat(
            self._heartbeat_payload(),
            credentials,
        )
        await self._report_installer_telemetry(credentials)
        await self._process_one_node_job(credentials)

        logger.info(
            json.dumps(
                {
                    "event": "heartbeat_success",
                    "node_id": credentials.node_id,
                    "status": response.get("status"),
                    "last_seen_at": response.get("last_seen_at"),
                }
            )
        )

    async def run(self, once: bool = False) -> None:
        self._event_loop = asyncio.get_running_loop()
        configure_logging(self.settings.agent.log_level)
        self._install_signal_handlers()
        self.state.transition(AgentState.CONFIGURED)
        plugins = self.plugin_manager.load_all()

        logger.info(
            json.dumps(
                {
                    "event": "agent_started",
                    "version": __version__,
                    "state": self.state.current,
                    "identity": asdict(self.identity),
                    "observation_only": self.settings.agent.observation_only,
                    "plugins": [
                        {"name": p.name, "version": p.version}
                        for p in plugins
                    ],
                },
                default=str,
            )
        )

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

        if not self.credential_store.exists():
            raise RuntimeError(
                "Heartbeat is enabled but the node is not enrolled. "
                "Run with --enroll first."
            )

        await self._heartbeat_loop()
        self.state.transition(AgentState.STOPPED)

    async def _heartbeat_loop(self) -> None:
        credentials = self.credential_store.load()

        while not self.stop_event.is_set():
            self.state.transition(AgentState.CONNECTING)
            try:
                await self.client.heartbeat(
                    self._heartbeat_payload(),
                    credentials,
                )
                await self._report_installer_telemetry(credentials)
                await self._sync_desired_state(credentials)
                await self._report_provisioning_state(credentials)
                await self._run_desired_image_build()
                await self._report_provisioning_state(credentials)
                await self._process_one_node_job(credentials)
                self.state.transition(AgentState.CONNECTED)
                logger.info(
                    json.dumps(
                        {
                            "event": "heartbeat_success",
                            "node_id": credentials.node_id,
                        }
                    )
                )
            except Exception as exc:
                self.state.transition(AgentState.DISCONNECTED)
                logger.warning(
                    json.dumps(
                        {
                            "event": "heartbeat_failed",
                            "node_id": credentials.node_id,
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

    def request_stop(self) -> None:
        """Request runtime shutdown safely from any thread."""
        loop = self._event_loop

        if loop is not None and loop.is_running():
            loop.call_soon_threadsafe(self.stop_event.set)
            return

        self.stop_event.set()

    def _install_signal_handlers(self) -> None:
        if platform.system() == "Windows":
            return

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, self.stop_event.set)
            except NotImplementedError:
                pass
