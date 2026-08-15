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
            "NVIDIA GeForce RTX 3080, 595.95\n"
            "NVIDIA GeForce RTX 5070 Ti, 595.95\n"
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
