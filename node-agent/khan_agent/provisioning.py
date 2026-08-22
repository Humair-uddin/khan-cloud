from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Iterable

import httpx


class ProvisioningStage(StrEnum):
    CONNECTED = "connected"
    QUALIFYING = "qualifying"
    DOWNLOADING = "downloading"
    BUILDING_IMAGE = "building_image"
    CONFIGURING_VM = "configuring_vm"
    CONFIGURING_GPU = "configuring_gpu"
    INSTALLING_RUNTIME = "installing_runtime"
    VALIDATING = "validating"
    READY = "ready"
    DEGRADED = "degraded"
    FAILED_RETRYABLE = "failed_retryable"
    FAILED_MANUAL_ACTION = "failed_manual_action"


@dataclass
class ProvisioningState:
    deployment_id: str = ""
    stage: str = ProvisioningStage.CONNECTED.value
    status: str = "idle"
    progress: float = 0.0
    downloaded_bytes: int = 0
    total_bytes: int = 0
    bytes_per_second: float = 0.0
    eta_seconds: int | None = None
    last_checkpoint: str = ""
    retry_count: int = 0
    desired_image_version: str = ""
    message: str = ""
    updated_at: float = field(default_factory=time.time)

    def as_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["progress"] = max(0.0, min(float(payload["progress"]), 1.0))
        return payload


class ProvisioningStateStore:
    def __init__(self, state_directory: Path) -> None:
        self.directory = Path(state_directory) / "provisioning"
        self.path = self.directory / "deployment-state.json"

    def load(self) -> ProvisioningState:
        if not self.path.exists():
            return ProvisioningState()
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        allowed = ProvisioningState.__dataclass_fields__.keys()
        return ProvisioningState(**{k: v for k, v in raw.items() if k in allowed})

    def save(self, state: ProvisioningState) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        state.updated_at = time.time()
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(state.as_payload(), indent=2, sort_keys=True), encoding="utf-8")
        os.replace(temp, self.path)


@dataclass(frozen=True)
class ArtifactSpec:
    artifact_id: str
    url: str
    destination: Path
    sha256: str
    total_bytes: int = 0


class ArtifactVerificationError(RuntimeError):
    pass


class ResumableArtifactDownloader:
    """HTTP range downloader with durable partial files and final SHA-256 verification."""

    def __init__(self, *, timeout_seconds: float = 60.0, chunk_bytes: int = 4 * 1024 * 1024) -> None:
        self.timeout_seconds = timeout_seconds
        self.chunk_bytes = max(256 * 1024, int(chunk_bytes))

    @staticmethod
    def sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    def download(self, spec: ArtifactSpec, *, on_progress=None) -> Path:
        destination = Path(spec.destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        partial = destination.with_suffix(destination.suffix + ".partial")
        start = partial.stat().st_size if partial.exists() else 0
        headers = {"Range": f"bytes={start}-"} if start else {}
        began = time.monotonic()
        initial = start
        total = int(spec.total_bytes or 0)

        with httpx.stream("GET", spec.url, headers=headers, timeout=self.timeout_seconds, follow_redirects=True) as response:
            if start and response.status_code == 200:
                partial.unlink(missing_ok=True)
                start = 0
                initial = 0
            elif start and response.status_code != 206:
                response.raise_for_status()
            else:
                response.raise_for_status()

            if not total:
                if response.status_code == 206:
                    content_range = response.headers.get("content-range", "")
                    if "/" in content_range:
                        try:
                            total = int(content_range.rsplit("/", 1)[1])
                        except ValueError:
                            total = 0
                if not total:
                    try:
                        total = start + int(response.headers.get("content-length", "0"))
                    except ValueError:
                        total = 0

            mode = "ab" if start else "wb"
            written = start
            with partial.open(mode) as handle:
                for chunk in response.iter_bytes(self.chunk_bytes):
                    if not chunk:
                        continue
                    handle.write(chunk)
                    handle.flush()
                    written += len(chunk)
                    elapsed = max(time.monotonic() - began, 0.001)
                    speed = max((written - initial) / elapsed, 0.0)
                    progress = (written / total) if total else 0.0
                    eta = int((total - written) / speed) if total and speed > 0 else None
                    if on_progress:
                        on_progress(written, total, speed, eta, progress)

        actual = self.sha256(partial)
        expected = spec.sha256.lower().strip()
        if expected and actual.lower() != expected:
            raise ArtifactVerificationError(
                f"SHA-256 mismatch for {spec.artifact_id}: expected {expected}, got {actual}"
            )
        os.replace(partial, destination)
        return destination


@dataclass(frozen=True)
class ResourceCapacity:
    mode: str
    cpu_total: int
    cpu_reserved: int
    cpu_sellable: int
    memory_total_bytes: int
    memory_reserved_bytes: int
    memory_sellable_bytes: int
    gpu_total_units: int
    gpu_reserved_units: int
    gpu_sellable_units: int

    def as_dict(self) -> dict[str, int | str]:
        return asdict(self)


def calculate_resource_capacity(
    *,
    mode: str,
    cpu_total: int,
    memory_total_bytes: int,
    gpu_total_units: int = 1000,
    owner_active: bool = False,
) -> ResourceCapacity:
    normalized = (mode or "shared").lower()
    if normalized == "private":
        cpu_fraction = memory_fraction = gpu_fraction = 1.0
    elif normalized == "dedicated":
        cpu_fraction, memory_fraction, gpu_fraction = 0.08, 0.08, 0.05
    elif normalized == "available":
        cpu_fraction, memory_fraction, gpu_fraction = 0.15, 0.15, 0.10
    else:  # shared
        if owner_active:
            cpu_fraction, memory_fraction, gpu_fraction = 0.55, 0.45, 0.60
        else:
            cpu_fraction, memory_fraction, gpu_fraction = 0.30, 0.30, 0.30

    cpu_reserved = min(cpu_total, max(0, round(cpu_total * cpu_fraction)))
    memory_reserved = min(memory_total_bytes, max(0, round(memory_total_bytes * memory_fraction)))
    gpu_reserved = min(gpu_total_units, max(0, round(gpu_total_units * gpu_fraction)))
    return ResourceCapacity(
        mode=normalized,
        cpu_total=cpu_total,
        cpu_reserved=cpu_reserved,
        cpu_sellable=max(cpu_total - cpu_reserved, 0),
        memory_total_bytes=memory_total_bytes,
        memory_reserved_bytes=memory_reserved,
        memory_sellable_bytes=max(memory_total_bytes - memory_reserved, 0),
        gpu_total_units=gpu_total_units,
        gpu_reserved_units=gpu_reserved,
        gpu_sellable_units=max(gpu_total_units - gpu_reserved, 0),
    )
