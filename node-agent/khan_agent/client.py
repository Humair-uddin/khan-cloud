from __future__ import annotations

from typing import Any

import httpx

from khan_agent.config import AgentSettings


class ControlPlaneClient:
    def __init__(self, settings: AgentSettings) -> None:
        self.settings = settings
        self.base_url = str(settings.agent.control_plane_url).rstrip("/")

    async def heartbeat(self, payload: dict[str, Any]) -> dict[str, Any]:
        headers: dict[str, str] = {}
        if self.settings.security.node_token:
            headers["Authorization"] = f"Bearer {self.settings.security.node_token}"

        async with httpx.AsyncClient(
            timeout=self.settings.agent.request_timeout_seconds,
            verify=self.settings.security.verify_tls,
        ) as client:
            response = await client.post(
                f"{self.base_url}{self.settings.heartbeat.endpoint}",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            if not response.content:
                return {}
            return response.json()
