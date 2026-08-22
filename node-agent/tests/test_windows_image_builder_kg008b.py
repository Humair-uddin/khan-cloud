import json
from pathlib import Path
from unittest.mock import patch

from khan_agent.provisioning import ProvisioningStateStore
from khan_agent.windows_image_builder import WindowsGoldenImageBuilder, WindowsImageBuildPlan


def plan(tmp_path: Path):
    iso = tmp_path / "win.iso"; iso.write_bytes(b"iso")
    return WindowsImageBuildPlan("dep-1", "win11-v1", iso, tmp_path/"golden.vhdx", tmp_path/"work")


def test_plan_requires_core_fields():
    try: WindowsImageBuildPlan.from_dict({})
    except Exception as exc: assert "Missing image-build fields" in str(exc)
    else: raise AssertionError("expected failure")


def test_builder_resumes_completed_checkpoints(tmp_path: Path):
    p = plan(tmp_path); store = ProvisioningStateStore(tmp_path/"state"); calls=[]
    def runner(cmd, **kwargs):
        calls.append(cmd[cmd.index("-Stage")+1])
        if calls[-1] == "finalize": p.output_vhdx.write_bytes(b"vhdx")
        class R: returncode=0; stdout="ok"; stderr=""
        return R()
    b=WindowsGoldenImageBuilder(store, worker_script=tmp_path/"worker.ps1", runner=runner)
    b.worker_script.write_text("# worker")
    p.workspace.mkdir(); (p.workspace/"image-build-checkpoints.json").write_text(json.dumps({"deployment_id":"dep-1","image_version":"win11-v1","completed":["preflight"]}))
    with patch("khan_agent.windows_image_builder.platform.system", return_value="Windows"):
        assert b.build(p) == p.output_vhdx
    assert calls == ["apply_windows","boot_files","finalize"]
    state=store.load(); assert state.last_checkpoint == "golden_vhdx_ready"; assert state.status == "ready_for_vm"


def test_failure_is_retryable_and_increments_counter(tmp_path: Path):
    p=plan(tmp_path); store=ProvisioningStateStore(tmp_path/"state"); worker=tmp_path/"worker.ps1"; worker.write_text("#")
    def runner(*args, **kwargs):
        class R: returncode=1; stdout=""; stderr="boom"
        return R()
    b=WindowsGoldenImageBuilder(store, worker_script=worker, runner=runner)
    with patch("khan_agent.windows_image_builder.platform.system", return_value="Windows"):
        try: b.build(p)
        except Exception: pass
    state=store.load(); assert state.status == "failed_retryable"; assert state.retry_count == 1


def test_windows_worker_is_windows_powershell_51_compatible():
    from pathlib import Path

    worker = (
        Path(__file__).resolve().parents[1]
        / "deploy"
        / "build-windows-golden-image.ps1"
    )

    text = worker.read_text(encoding="utf-8")

    assert "-LeafBase" not in text
    assert "[System.IO.Path]::GetFileNameWithoutExtension($OutputVhdx)" in text
