from pathlib import Path

from khan_agent.provisioning import (
    ProvisioningState,
    ProvisioningStateStore,
    calculate_resource_capacity,
)


def test_provisioning_state_round_trip(tmp_path: Path):
    store = ProvisioningStateStore(tmp_path)
    state = ProvisioningState(
        deployment_id="dep-1", stage="downloading", status="running",
        progress=0.5, downloaded_bytes=50, total_bytes=100,
        last_checkpoint="chunk-10", retry_count=2,
    )
    store.save(state)
    loaded = store.load()
    assert loaded.deployment_id == "dep-1"
    assert loaded.stage == "downloading"
    assert loaded.downloaded_bytes == 50
    assert loaded.last_checkpoint == "chunk-10"
    assert store.path.exists()


def test_shared_owner_active_reserves_more_gpu():
    idle = calculate_resource_capacity(mode="shared", cpu_total=16, memory_total_bytes=64_000, owner_active=False)
    active = calculate_resource_capacity(mode="shared", cpu_total=16, memory_total_bytes=64_000, owner_active=True)
    assert active.gpu_reserved_units > idle.gpu_reserved_units
    assert active.gpu_sellable_units < idle.gpu_sellable_units


def test_dedicated_keeps_safety_reserve():
    cap = calculate_resource_capacity(mode="dedicated", cpu_total=16, memory_total_bytes=64_000)
    assert cap.cpu_sellable > cap.cpu_reserved
    assert 0 < cap.gpu_reserved_units < cap.gpu_total_units
