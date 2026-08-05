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
        token = self.settings.security.enrollment_token
        if not token:
            raise RuntimeError(
                "Enrollment token is missing. Set security.enrollment_token "
                "in the private agent configuration."
            )

        async with httpx.AsyncClient(
            timeout=self.settings.agent.request_timeout_seconds,
            verify=self.settings.security.verify_tls,
        ) as client:
            response = await client.post(
                f"{self.base_url}{self.settings.enrollment.endpoint}",
                json=payload,
                headers={"X-Enrollment-Token": token},
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
