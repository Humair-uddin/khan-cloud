from __future__ import annotations

import json
import os
import platform
import subprocess
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Callable

from khan_agent.provisioning import ProvisioningStage, ProvisioningState, ProvisioningStateStore


class WindowsImageBuildError(RuntimeError):
    pass


@dataclass(frozen=True)
class WindowsImageBuildPlan:
    deployment_id: str
    image_version: str
    iso_path: Path
    output_vhdx: Path
    workspace: Path
    edition: str = "Windows 11 Pro"
    disk_size_gb: int = 80
    generation: int = 2

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "WindowsImageBuildPlan":
        required = ("deployment_id", "image_version", "iso_path", "output_vhdx", "workspace")
        missing = [key for key in required if not str(raw.get(key) or "").strip()]
        if missing:
            raise WindowsImageBuildError(f"Missing image-build fields: {', '.join(missing)}")
        return cls(
            deployment_id=str(raw["deployment_id"]),
            image_version=str(raw["image_version"]),
            iso_path=Path(str(raw["iso_path"])),
            output_vhdx=Path(str(raw["output_vhdx"])),
            workspace=Path(str(raw["workspace"])),
            edition=str(raw.get("edition") or "Windows 11 Pro"),
            disk_size_gb=max(40, int(raw.get("disk_size_gb") or 80)),
            generation=int(raw.get("generation") or 2),
        )


class WindowsGoldenImageBuilder:
    """Durable Windows ISO -> generalized golden VHDX orchestration.

    The PowerShell worker owns Windows storage/DISM operations. This class owns
    idempotency, checkpoints, recovery and control-plane progress state.
    """

    CHECKPOINTS = ("preflight", "apply_windows", "boot_files", "finalize")

    def __init__(
        self,
        state_store: ProvisioningStateStore,
        *,
        worker_script: Path,
        runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    ) -> None:
        self.state_store = state_store
        self.worker_script = Path(worker_script)
        self.runner = runner

    def _checkpoint_path(self, plan: WindowsImageBuildPlan) -> Path:
        return plan.workspace / "image-build-checkpoints.json"

    def _load_checkpoints(self, plan: WindowsImageBuildPlan) -> set[str]:
        path = self._checkpoint_path(plan)
        if not path.exists():
            return set()
        raw = json.loads(path.read_text(encoding="utf-8"))
        if raw.get("deployment_id") != plan.deployment_id or raw.get("image_version") != plan.image_version:
            return set()
        return set(raw.get("completed", []))

    def _save_checkpoints(self, plan: WindowsImageBuildPlan, completed: set[str]) -> None:
        plan.workspace.mkdir(parents=True, exist_ok=True)
        path = self._checkpoint_path(plan)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({
            "deployment_id": plan.deployment_id,
            "image_version": plan.image_version,
            "completed": sorted(completed),
            "updated_at": time.time(),
        }, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(tmp, path)

    def _state(self, plan: WindowsImageBuildPlan, *, progress: float, checkpoint: str, message: str) -> None:
        state = self.state_store.load()
        state.deployment_id = plan.deployment_id
        state.desired_image_version = plan.image_version
        state.stage = ProvisioningStage.BUILDING_IMAGE.value
        state.status = "running"
        state.progress = progress
        state.last_checkpoint = checkpoint
        state.message = message
        self.state_store.save(state)

    def _run_stage(self, plan: WindowsImageBuildPlan, stage: str) -> None:
        if platform.system() != "Windows":
            raise WindowsImageBuildError("Windows golden-image build requires a Windows Hyper-V host.")
        if not self.worker_script.is_file():
            raise WindowsImageBuildError(f"Image worker script missing: {self.worker_script}")
        command = [
            "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", str(self.worker_script),
            "-Stage", stage,
            "-IsoPath", str(plan.iso_path),
            "-OutputVhdx", str(plan.output_vhdx),
            "-Workspace", str(plan.workspace),
            "-Edition", plan.edition,
            "-DiskSizeGB", str(plan.disk_size_gb),
        ]
        result = self.runner(command, check=False, capture_output=True, text=True, timeout=7200)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "image worker failed").strip()[-2000:]
            raise WindowsImageBuildError(f"{stage} failed: {detail}")

    def build(self, plan: WindowsImageBuildPlan) -> Path:
        if not plan.iso_path.is_file():
            raise WindowsImageBuildError(f"Windows ISO not found: {plan.iso_path}")
        plan.workspace.mkdir(parents=True, exist_ok=True)
        plan.output_vhdx.parent.mkdir(parents=True, exist_ok=True)
        completed = self._load_checkpoints(plan)
        total = len(self.CHECKPOINTS)
        try:
            for index, checkpoint in enumerate(self.CHECKPOINTS):
                if checkpoint in completed:
                    continue
                self._state(plan, progress=index / total, checkpoint=checkpoint,
                            message=f"Windows image build: {checkpoint}")
                self._run_stage(plan, checkpoint)
                completed.add(checkpoint)
                self._save_checkpoints(plan, completed)
            if not plan.output_vhdx.is_file():
                raise WindowsImageBuildError("Image worker completed but golden VHDX is missing.")
            state = self.state_store.load()
            state.deployment_id = plan.deployment_id
            state.desired_image_version = plan.image_version
            state.stage = ProvisioningStage.CONFIGURING_VM.value
            state.status = "ready_for_vm"
            state.progress = 1.0
            state.last_checkpoint = "golden_vhdx_ready"
            state.message = f"Golden VHDX ready: {plan.output_vhdx}"
            self.state_store.save(state)
            return plan.output_vhdx
        except Exception as exc:
            state = self.state_store.load()
            state.deployment_id = plan.deployment_id
            state.desired_image_version = plan.image_version
            state.stage = ProvisioningStage.FAILED_RETRYABLE.value
            state.status = "failed_retryable"
            state.retry_count += 1
            state.message = str(exc)[:500]
            self.state_store.save(state)
            raise
