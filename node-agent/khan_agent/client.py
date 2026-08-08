from __future__ import annotations

from typing import Any

import httpx

from khan_agent.config import AgentSettings
from khan_agent.credentials import NodeCredentials


class ControlPlaneClient:
    def __init__(self, settings: AgentSettings) -> None:
        self.settings = settings
        self.base_url = str(settings.agent.control_plane_url).rstrip("/")

    async def enroll(self, payload: dict[str, Any]) -> dict[str, Any]:
        deployment_code = self.settings.security.deployment_enrollment_code
        legacy_token = self.settings.security.enrollment_token

        if deployment_code:
            headers = {
                "X-Deployment-Enrollment-Code": deployment_code,
            }
        elif legacy_token:
            headers = {"X-Enrollment-Token": legacy_token}
        else:
            raise RuntimeError(
                "Enrollment credential is missing. Set "
                "security.deployment_enrollment_code."
            )

        async with httpx.AsyncClient(
            timeout=self.settings.agent.request_timeout_seconds,
            verify=self.settings.security.verify_tls,
        ) as client:
            response = await client.post(
                f"{self.base_url}{self.settings.enrollment.endpoint}",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            return response.json()

    async def heartbeat(
        self,
        payload: dict[str, Any],
        credentials: NodeCredentials,
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(
            timeout=self.settings.agent.request_timeout_seconds,
            verify=self.settings.security.verify_tls,
        ) as client:
            response = await client.post(
                f"{self.base_url}{self.settings.heartbeat.endpoint}",
                json=payload,
                headers={
                    "X-Node-ID": credentials.node_id,
                    "X-Node-Secret": credentials.node_secret,
                },
            )
            response.raise_for_status()
            return response.json()
    async def report_installation_event(
        self,
        payload: dict[str, Any],
        credentials: NodeCredentials,
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(
            timeout=self.settings.agent.request_timeout_seconds,
            verify=self.settings.security.verify_tls,
        ) as client:
            response = await client.post(
                f"{self.base_url}{self.settings.telemetry.endpoint}",
                json=payload,
                headers={
                    "X-Node-ID": credentials.node_id,
                    "X-Node-Secret": credentials.node_secret,
                },
            )
            response.raise_for_status()
            return response.json()

    async def next_job(self, credentials: NodeCredentials) -> dict[str, Any] | None:
        async with httpx.AsyncClient(
            timeout=self.settings.agent.request_timeout_seconds,
            verify=self.settings.security.verify_tls,
        ) as client:
            response = await client.get(
                f"{self.base_url}{self.settings.virtualization.jobs_endpoint}",
                headers={
                    "X-Node-ID": credentials.node_id,
                    "X-Node-Secret": credentials.node_secret,
                },
            )
            if response.status_code == 204:
                return None
            response.raise_for_status()
            return response.json()

    async def report_job_result(
        self,
        job_id: str,
        payload: dict[str, Any],
        credentials: NodeCredentials,
    ) -> dict[str, Any]:
        endpoint = self.settings.virtualization.job_result_endpoint_prefix.rstrip("/")
        async with httpx.AsyncClient(
            timeout=self.settings.agent.request_timeout_seconds,
            verify=self.settings.security.verify_tls,
        ) as client:
            response = await client.post(
                f"{self.base_url}{endpoint}/{job_id}/result",
                json=payload,
                headers={
                    "X-Node-ID": credentials.node_id,
                    "X-Node-Secret": credentials.node_secret,
                },
            )
            response.raise_for_status()
            return response.json()
