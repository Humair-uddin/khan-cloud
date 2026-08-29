from pathlib import Path
from types import SimpleNamespace

from app.services import gaming_service


def test_khan_cloud_capacity_wins_before_stronger_marketplace_gpu():
    khan = gaming_service._gaming_placement_rank(
        ownership_type="khan_cloud",
        gpu_vram_mb=10240,
        available_memory_bytes=16 * 1024**3,
    )

    marketplace = gaming_service._gaming_placement_rank(
        ownership_type="third_party_provider",
        gpu_vram_mb=24576,
        available_memory_bytes=128 * 1024**3,
    )

    assert khan < marketplace


def test_stronger_gpu_wins_inside_same_ownership_tier():
    smaller = gaming_service._gaming_placement_rank(
        ownership_type="khan_cloud",
        gpu_vram_mb=10240,
        available_memory_bytes=128 * 1024**3,
    )

    larger = gaming_service._gaming_placement_rank(
        ownership_type="khan_cloud",
        gpu_vram_mb=24576,
        available_memory_bytes=16 * 1024**3,
    )

    assert larger < smaller


def test_unknown_ownership_is_last_resort():
    known = gaming_service._gaming_placement_rank(
        ownership_type="third_party_provider",
        gpu_vram_mb=8192,
        available_memory_bytes=1,
    )

    unknown = gaming_service._gaming_placement_rank(
        ownership_type="unknown",
        gpu_vram_mb=49152,
        available_memory_bytes=1024**4,
    )

    assert known < unknown


def test_ownership_is_derived_from_existing_deployment_profile():
    profile = SimpleNamespace(
        ownership_type="khan_cloud",
    )

    class FakeDb:
        def get(self, model, identifier):
            assert identifier == "profile-1"
            return profile

    node = SimpleNamespace(
        deployment_profile_id="profile-1",
    )

    assert (
        gaming_service._node_ownership_type(
            FakeDb(),
            node,
        )
        == "khan_cloud"
    )


def test_placement_metadata_records_scheduler_decision():
    profile = SimpleNamespace(
        ownership_type="third_party_provider",
    )

    class FakeDb:
        def get(self, model, identifier):
            return profile

    node = SimpleNamespace(
        deployment_profile_id="profile-1",
    )

    value = gaming_service._gaming_placement_metadata(
        FakeDb(),
        node,
    )

    assert value == {
        "policy_version": "kg009-v1",
        "ownership_type": "third_party_provider",
        "khan_owned": False,
        "fallback_capacity": True,
    }


def test_scheduler_keeps_atomic_capacity_lock():
    source = Path(
        gaming_service.__file__
    ).read_text()

    assert ".with_for_update(of=NodeCapacity)" in source
    assert '"placement": _gaming_placement_metadata(' in source


def test_ownership_never_replaces_hard_admission_gates():
    source = Path(
        gaming_service.__file__
    ).read_text()

    qualification = source.index(
        "if qualified_nodes is not None"
    )
    capacity = source.index(
        "if not has_capacity(",
        qualification,
    )
    ownership = source.index(
        "ownership_type = _node_ownership_type(",
        capacity,
    )

    assert qualification < capacity < ownership
