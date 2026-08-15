from pathlib import Path

from kc_installer.models import Manifest
from kc_installer.preflight import run_preflight


def manifest_with(**compatibility) -> Manifest:
    return Manifest.model_validate(
        {
            "feature_pack": {
                "id": "FP-PREFLIGHT",
                "name": "Preflight Test",
                "version": "1.0.0",
            },
            "components": {},
            "operations": {
                "require_clean_git": False,
            },
            "compatibility": compatibility,
        }
    )


def test_preflight_accepts_current_architecture(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "kc_installer.preflight.platform.machine",
        lambda: "x86_64",
    )

    manifest = manifest_with(
        architectures=["x86_64"],
    )

    results = run_preflight(manifest, tmp_path)

    assert len(results) == 1
    assert results[0].passed is True


def test_preflight_rejects_wrong_architecture(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "kc_installer.preflight.platform.machine",
        lambda: "arm64",
    )

    manifest = manifest_with(
        architectures=["x86_64"],
    )

    results = run_preflight(manifest, tmp_path)

    assert len(results) == 1
    assert results[0].passed is False


def test_preflight_detects_missing_command(
    tmp_path: Path,
) -> None:
    manifest = Manifest.model_validate(
        {
            "feature_pack": {
                "id": "FP-PREFLIGHT",
                "name": "Preflight Test",
                "version": "1.0.0",
            },
            "components": {},
            "operations": {
                "require_clean_git": False,
            },
            "preflight": {
                "required_commands": [
                    "khan-cloud-command-that-does-not-exist"
                ]
            },
        }
    )

    results = run_preflight(manifest, tmp_path)

    assert len(results) == 1
    assert results[0].passed is False
    assert results[0].actual == "missing"


def test_memory_mb_windows_uses_platform_adapter(monkeypatch):
    from kc_installer import preflight

    monkeypatch.setattr(preflight.os, "name", "nt")
    monkeypatch.setattr(
        preflight,
        "_windows_memory_mb",
        lambda: 32768,
    )

    assert preflight.memory_mb() == 32768


def test_memory_mb_posix_keeps_existing_detection(monkeypatch):
    from kc_installer import preflight

    monkeypatch.setattr(preflight.os, "name", "posix")
    monkeypatch.setattr(
        preflight.os,
        "sysconf",
        lambda name: {
            "SC_PAGE_SIZE": 4096,
            "SC_PHYS_PAGES": 2097152,
        }[name],
    )

    assert preflight.memory_mb() == 8192


def gaming_manifest_with_gpu(
    approved_models: list[str],
    *,
    required: bool = True,
) -> Manifest:
    return Manifest.model_validate(
        {
            "feature_pack": {
                "id": "FP-GAMING-WINDOWS",
                "name": "Windows Gaming Host",
                "version": "1.0.0",
            },
            "deployment": {
                "purpose": "gaming_host",
                "platform": "windows",
                "execution_backend": "windows_native",
                "streaming_backend": "sunshine",
            },
            "qualification": {
                "gpu": {
                    "required": required,
                    "qualification_mode": "allowlist",
                    "approved_models": approved_models,
                },
                "driver": {
                    "vendor": "nvidia",
                    "required": False,
                    "minimum_version": None,
                    "approved_branches": [],
                },
                "workloads": {
                    "primary": ["gaming"],
                    "optional_interruptible": [
                        "ai",
                        "rendering",
                        "editing",
                    ],
                },
            },
            "components": {},
        }
    )


def test_detect_nvidia_gpus_parses_nvidia_smi(monkeypatch):
    from kc_installer import preflight

    class Completed:
        returncode = 0
        stdout = (
            "NVIDIA GeForce RTX 3080, 595.95, 10240\n"
            "NVIDIA GeForce RTX 5070 Ti, 595.95, 16303\n"
        )
        stderr = ""

    monkeypatch.setattr(
        preflight.subprocess,
        "run",
        lambda *args, **kwargs: Completed(),
    )

    devices = preflight.detect_nvidia_gpus()

    assert len(devices) == 2

    assert devices[0].model == "NVIDIA GeForce RTX 3080"
    assert devices[0].driver_version == "595.95"
    assert devices[0].memory_total_mb == 10240
    assert devices[0].operational is True
    assert "hardware_video_encode" in devices[0].capabilities

    assert devices[1].model == "NVIDIA GeForce RTX 5070 Ti"
    assert devices[1].driver_version == "595.95"
    assert devices[1].memory_total_mb == 16303
    assert devices[1].operational is True
    assert devices[0].model == "NVIDIA GeForce RTX 3080"
    assert devices[0].driver_version == "595.95"
    assert devices[1].model == "NVIDIA GeForce RTX 5070 Ti"


def test_gpu_allowlist_accepts_approved_gpu(tmp_path, monkeypatch):
    from kc_installer import preflight

    manifest = gaming_manifest_with_gpu(
        ["NVIDIA GeForce RTX 3080"]
    )

    monkeypatch.setattr(
        preflight,
        "detect_nvidia_gpus",
        lambda: [
            preflight.NvidiaGPU(
                model="NVIDIA GeForce RTX 3080",
                driver_version="595.95",
            )
        ],
    )

    results = run_preflight(manifest, tmp_path)

    gpu_result = next(
        result
        for result in results
        if result.name == "gpu_qualification"
    )

    assert gpu_result.passed is True
    assert gpu_result.actual == "NVIDIA GeForce RTX 3080"


def test_gpu_allowlist_rejects_unapproved_gpu(tmp_path, monkeypatch):
    from kc_installer import preflight

    manifest = gaming_manifest_with_gpu(
        ["NVIDIA GeForce RTX 3080"]
    )

    monkeypatch.setattr(
        preflight,
        "detect_nvidia_gpus",
        lambda: [
            preflight.NvidiaGPU(
                model="NVIDIA GeForce GTX 1080",
                driver_version="576.80",
            )
        ],
    )

    results = run_preflight(manifest, tmp_path)

    gpu_result = next(
        result
        for result in results
        if result.name == "gpu_qualification"
    )

    assert gpu_result.passed is False
    assert gpu_result.actual == "NVIDIA GeForce GTX 1080"


def test_required_gpu_fails_when_no_nvidia_gpu_detected(
    tmp_path,
    monkeypatch,
):
    from kc_installer import preflight

    manifest = gaming_manifest_with_gpu(
        ["NVIDIA GeForce RTX 3080"]
    )

    monkeypatch.setattr(
        preflight,
        "detect_nvidia_gpus",
        lambda: [],
    )

    results = run_preflight(manifest, tmp_path)

    gpu_result = next(
        result
        for result in results
        if result.name == "gpu_qualification"
    )

    assert gpu_result.passed is False
    assert gpu_result.actual == "not detected"


def test_legacy_manifest_does_not_probe_gpu(tmp_path, monkeypatch):
    from kc_installer import preflight

    manifest = manifest_with()

    monkeypatch.setattr(
        preflight,
        "detect_nvidia_gpus",
        lambda: (_ for _ in ()).throw(
            AssertionError("GPU detection must not run")
        ),
        raising=False,
    )

    results = run_preflight(manifest, tmp_path)

    assert not any(
        result.name == "gpu_qualification"
        for result in results
    )


def gaming_manifest_with_driver(
    *,
    minimum_version: str | None = None,
    approved_branches: list[str] | None = None,
) -> Manifest:
    return Manifest.model_validate(
        {
            "feature_pack": {
                "id": "FP-GAMING-WINDOWS",
                "name": "Windows Gaming Host",
                "version": "1.0.0",
            },
            "deployment": {
                "purpose": "gaming_host",
                "platform": "windows",
                "execution_backend": "windows_native",
                "streaming_backend": "sunshine",
            },
            "qualification": {
                "gpu": {
                    "required": True,
                    "qualification_mode": "allowlist",
                    "approved_models": [
                        "NVIDIA GeForce RTX 3080",
                    ],
                },
                "driver": {
                    "vendor": "nvidia",
                    "required": True,
                    "minimum_version": minimum_version,
                    "approved_branches": approved_branches or [],
                },
            },
            "components": {},
        }
    )


def test_driver_qualification_accepts_minimum_version(
    tmp_path,
    monkeypatch,
):
    from kc_installer import preflight

    manifest = gaming_manifest_with_driver(
        minimum_version="595.00",
    )

    monkeypatch.setattr(
        preflight,
        "detect_nvidia_gpus",
        lambda: [
            preflight.NvidiaGPU(
                model="NVIDIA GeForce RTX 3080",
                driver_version="595.95",
            )
        ],
    )

    results = run_preflight(manifest, tmp_path)

    driver_result = next(
        result
        for result in results
        if result.name == "driver_qualification"
    )

    assert driver_result.passed is True
    assert driver_result.actual == "595.95"


def test_driver_qualification_rejects_below_minimum(
    tmp_path,
    monkeypatch,
):
    from kc_installer import preflight

    manifest = gaming_manifest_with_driver(
        minimum_version="595.00",
    )

    monkeypatch.setattr(
        preflight,
        "detect_nvidia_gpus",
        lambda: [
            preflight.NvidiaGPU(
                model="NVIDIA GeForce RTX 3080",
                driver_version="576.80",
            )
        ],
    )

    results = run_preflight(manifest, tmp_path)

    driver_result = next(
        result
        for result in results
        if result.name == "driver_qualification"
    )

    assert driver_result.passed is False
    assert driver_result.actual == "576.80"


def test_driver_qualification_accepts_approved_branch(
    tmp_path,
    monkeypatch,
):
    from kc_installer import preflight

    manifest = gaming_manifest_with_driver(
        approved_branches=["595"],
    )

    monkeypatch.setattr(
        preflight,
        "detect_nvidia_gpus",
        lambda: [
            preflight.NvidiaGPU(
                model="NVIDIA GeForce RTX 3080",
                driver_version="595.95",
            )
        ],
    )

    results = run_preflight(manifest, tmp_path)

    driver_result = next(
        result
        for result in results
        if result.name == "driver_qualification"
    )

    assert driver_result.passed is True


def test_required_driver_fails_when_driver_is_unavailable(
    tmp_path,
    monkeypatch,
):
    from kc_installer import preflight

    manifest = gaming_manifest_with_driver()

    monkeypatch.setattr(
        preflight,
        "detect_nvidia_gpus",
        lambda: [],
    )

    results = run_preflight(manifest, tmp_path)

    driver_result = next(
        result
        for result in results
        if result.name == "driver_qualification"
    )

    assert driver_result.passed is False
    assert driver_result.actual == "not detected"


def capability_gaming_manifest(
    *,
    minimum_vram_mb: int = 8192,
) -> Manifest:
    return Manifest.model_validate(
        {
            "feature_pack": {
                "id": "FP-GAMING-WINDOWS-CAPABILITY",
                "name": "Windows Gaming Host Capability Policy",
                "version": "1.0.0",
            },
            "deployment": {
                "purpose": "gaming_host",
                "platform": "windows",
                "execution_backend": "windows_native",
                "streaming_backend": "sunshine",
            },
            "qualification": {
                "gpu": {
                    "required": True,
                    "qualification_mode": "capability",
                    "vendor": "nvidia",
                    "minimum_vram_mb": minimum_vram_mb,
                    "required_capabilities": [
                        "hardware_video_encode",
                    ],
                    "require_operational_gpu": True,
                    "quality_policy": {
                        "minimum_experience_tier": "standard",
                        "tiers": {
                            "standard": {
                                "minimum_vram_mb": 8192,
                            },
                            "premium": {
                                "minimum_vram_mb": 10240,
                            },
                            "ultra": {
                                "minimum_vram_mb": 16384,
                            },
                        },
                    },
                },
                "driver": {
                    "vendor": "nvidia",
                    "required": True,
                    "management": "preserve_existing",
                    "require_operational": True,
                    "automatic_upgrade": False,
                },
            },
            "components": {},
        }
    )


def test_capability_policy_accepts_working_10gb_rtx3080(
    tmp_path,
    monkeypatch,
):
    from kc_installer import preflight

    manifest = capability_gaming_manifest()

    monkeypatch.setattr(
        preflight,
        "detect_nvidia_gpus",
        lambda: [
            preflight.NvidiaGPU(
                model="NVIDIA GeForce RTX 3080",
                driver_version="595.95",
                memory_total_mb=10240,
                operational=True,
                capabilities=("hardware_video_encode",),
            )
        ],
    )

    results = run_preflight(manifest, tmp_path)

    gpu = next(
        result
        for result in results
        if result.name == "gpu_qualification"
    )

    assert gpu.passed is True


def test_capability_policy_rejects_gpu_below_8gb(
    tmp_path,
    monkeypatch,
):
    from kc_installer import preflight

    manifest = capability_gaming_manifest()

    monkeypatch.setattr(
        preflight,
        "detect_nvidia_gpus",
        lambda: [
            preflight.NvidiaGPU(
                model="NVIDIA GeForce GTX TEST",
                driver_version="595.95",
                memory_total_mb=6144,
                operational=True,
                capabilities=("hardware_video_encode",),
            )
        ],
    )

    results = run_preflight(manifest, tmp_path)

    gpu = next(
        result
        for result in results
        if result.name == "gpu_qualification"
    )

    assert gpu.passed is False
    assert "8192" in gpu.required


def test_capability_policy_rejects_missing_encoder(
    tmp_path,
    monkeypatch,
):
    from kc_installer import preflight

    manifest = capability_gaming_manifest()

    monkeypatch.setattr(
        preflight,
        "detect_nvidia_gpus",
        lambda: [
            preflight.NvidiaGPU(
                model="NVIDIA GeForce TEST",
                driver_version="595.95",
                memory_total_mb=12288,
                operational=True,
                capabilities=(),
            )
        ],
    )

    results = run_preflight(manifest, tmp_path)

    gpu = next(
        result
        for result in results
        if result.name == "gpu_qualification"
    )

    assert gpu.passed is False


def test_capability_policy_rejects_non_operational_gpu(
    tmp_path,
    monkeypatch,
):
    from kc_installer import preflight

    manifest = capability_gaming_manifest()

    monkeypatch.setattr(
        preflight,
        "detect_nvidia_gpus",
        lambda: [
            preflight.NvidiaGPU(
                model="NVIDIA GeForce TEST",
                driver_version="595.95",
                memory_total_mb=12288,
                operational=False,
                capabilities=("hardware_video_encode",),
            )
        ],
    )

    results = run_preflight(manifest, tmp_path)

    gpu = next(
        result
        for result in results
        if result.name == "gpu_qualification"
    )

    assert gpu.passed is False


def test_gaming_driver_policy_preserves_working_customer_driver():
    manifest = capability_gaming_manifest()

    driver = manifest.qualification.driver

    assert driver.management == "preserve_existing"
    assert driver.require_operational is True
    assert driver.automatic_upgrade is False


def test_legacy_gpu_allowlist_manifest_remains_supported():
    manifest = gaming_manifest_with_gpu(
        ["NVIDIA GeForce RTX 3080"]
    )

    assert (
        manifest.qualification.gpu.qualification_mode
        == "allowlist"
    )


def test_experience_tier_classifier():
    from kc_installer.preflight import (
        classify_gpu_experience_tier,
    )

    policy = {
        "tiers": {
            "standard": {"minimum_vram_mb": 8192},
            "premium": {"minimum_vram_mb": 10240},
            "ultra": {"minimum_vram_mb": 16384},
        }
    }

    assert classify_gpu_experience_tier(6144, policy) is None
    assert (
        classify_gpu_experience_tier(8192, policy)
        == "standard"
    )
    assert (
        classify_gpu_experience_tier(10240, policy)
        == "premium"
    )
    assert (
        classify_gpu_experience_tier(24576, policy)
        == "ultra"
    )
