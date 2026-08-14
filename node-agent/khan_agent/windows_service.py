from __future__ import annotations

import asyncio
from pathlib import Path

import servicemanager
import win32event
import win32service
import win32serviceutil

from khan_agent.config import AgentSettings
from khan_agent.runtime import AgentRuntime


class KhanCloudAgentService(win32serviceutil.ServiceFramework):
    _svc_name_ = "KhanCloudAgent"
    _svc_display_name_ = "Khan Cloud Agent"
    _svc_description_ = "Khan Cloud managed node agent"

    def __init__(self, args):
        super().__init__(args)
        self.stop_event = win32event.CreateEvent(None, 0, 0, None)
        self.runtime: AgentRuntime | None = None

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)

        if self.runtime is not None:
            self.runtime.request_stop()

        win32event.SetEvent(self.stop_event)

    def SvcDoRun(self):
        servicemanager.LogInfoMsg("Khan Cloud Agent service starting")

        program_data = Path(
            __import__("os").environ.get("ProgramData", r"C:\ProgramData")
        )
        config_path = (
            program_data / "KhanCloud" / "Agent" / "config.yaml"
        )

        settings = AgentSettings.load(config_path)
        self.runtime = AgentRuntime(settings)

        try:
            asyncio.run(self.runtime.run())
        except Exception as exc:
            servicemanager.LogErrorMsg(
                f"Khan Cloud Agent service failed: {exc}"
            )
            raise
        finally:
            servicemanager.LogInfoMsg("Khan Cloud Agent service stopped")


def main() -> None:
    win32serviceutil.HandleCommandLine(KhanCloudAgentService)


if __name__ == "__main__":
    main()
