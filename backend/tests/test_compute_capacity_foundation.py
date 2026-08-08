from types import SimpleNamespace

from app.services.compute_service import calculate_host_reserve, has_capacity, readiness_reasons

GIB = 1024 ** 3


def capacity(**overrides):
    data = dict(
        kvm_available=True,
        libvirt_available=True,
        execution_enabled=True,
        cpu_allocatable=120,
        memory_allocatable_bytes=24 * GIB,
        storage_allocatable_bytes=200 * GIB,
    )
    data.update(overrides)
    return SimpleNamespace(**data)


def node(**overrides):
    data = dict(
        lifecycle_state="approved",
        connectivity_state="online",
        intended_purpose="vps_infrastructure",
    )
    data.update(overrides)
    return SimpleNamespace(**data)


def test_r7425_sized_host_reserves_cpu_and_memory_for_host():
    cpu, memory, storage = calculate_host_reserve(128, 31 * GIB, 300 * GIB)
    assert cpu == 8
    assert memory >= 2 * GIB
    assert memory < 5 * GIB
    assert storage == 30 * GIB


def test_ready_vps_host_has_no_blocking_reasons():
    assert readiness_reasons(node(), capacity()) == []


def test_kvm_and_libvirt_are_independent_gates():
    reasons = readiness_reasons(node(), capacity(kvm_available=False, libvirt_available=False))
    assert "kvm_unavailable" in reasons
    assert "libvirt_unavailable" in reasons


def test_execution_policy_must_be_enabled_even_when_kvm_exists():
    reasons = readiness_reasons(node(), capacity(execution_enabled=False))
    assert reasons == ["vps_execution_disabled"]


def test_offline_or_wrong_purpose_node_cannot_schedule():
    reasons = readiness_reasons(
        node(connectivity_state="offline", intended_purpose="gpu_compute"),
        capacity(),
    )
    assert "node_not_online" in reasons
    assert "node_not_vps_infrastructure" in reasons


def test_capacity_check_prevents_overbooking():
    cap = SimpleNamespace(
        cpu_allocatable=120, cpu_allocated=118,
        memory_allocatable_bytes=24 * GIB, memory_allocated_bytes=23 * GIB,
        storage_allocatable_bytes=200 * GIB, storage_allocated_bytes=190 * GIB,
    )
    assert has_capacity(cap, cpu=2, memory_bytes=1 * GIB, storage_bytes=10 * GIB) is True
    assert has_capacity(cap, cpu=3, memory_bytes=1 * GIB, storage_bytes=10 * GIB) is False
    assert has_capacity(cap, cpu=2, memory_bytes=2 * GIB, storage_bytes=10 * GIB) is False
    assert has_capacity(cap, cpu=2, memory_bytes=1 * GIB, storage_bytes=11 * GIB) is False
