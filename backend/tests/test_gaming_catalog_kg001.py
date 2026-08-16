from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from app.services.gaming_catalog_service import (
    QUALIFICATION_MAX_AGE,
    _cpu_threads,
    _gpu_vram_values_mb,
    _maximum_gpu_vram_mb,
    _memory_mb,
    _sunshine_ready,
    qualification_is_fresh,
)


def _node(**overrides):
    values = {
        "inventory": {},
        "memory_total_bytes": 0,
        "cpu_logical_count": 0,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_kg001_models_exist():
    source = Path("app/models/gaming_catalog.py").read_text()
    assert "class GamingTitle" in source
    assert "class NodeGameInventory" in source
    assert "class NodeGameQualification" in source


def test_scheduler_uses_precomputed_game_qualification():
    source = Path(
        "app/services/gaming_service.py"
    ).read_text()

    assert "_qualified_node_ids" in source
    assert "qualification_is_fresh" in source
    assert "gaming_title=gaming_title" in source


def test_heartbeat_reconciles_gaming_inventory():
    source = Path("app/api/v1/nodes.py").read_text()
    assert "reconcile_node_gaming_inventory" in source


def test_gpu_qualification_uses_best_gpu():
    node = _node(
        inventory={
            "nvidia": {
                "gpus": [
                    {
                        "uuid": "GPU-small",
                        "memory_total_mib": 4096,
                    },
                    {
                        "uuid": "GPU-large",
                        "memory_total_mib": 10240,
                    },
                ]
            }
        }
    )

    assert _gpu_vram_values_mb(node) == [4096, 10240]
    assert _maximum_gpu_vram_mb(node) == 10240


def test_memory_and_cpu_inventory_contract():
    node = _node(
        inventory={
            "memory": {
                "total_bytes": 32 * 1024**3,
            },
            "cpu": {
                "logical_count": 32,
            },
        }
    )

    assert _memory_mb(node) == 32768
    assert _cpu_threads(node) == 32


def test_sunshine_requires_installed_and_ready():
    installed_only = _node(
        inventory={
            "gaming": {
                "streaming": {
                    "sunshine": {
                        "installed": True,
                        "ready": False,
                    }
                }
            }
        }
    )

    ready = _node(
        inventory={
            "gaming": {
                "streaming": {
                    "sunshine": {
                        "installed": True,
                        "ready": True,
                    }
                }
            }
        }
    )

    assert _sunshine_ready(installed_only) is False
    assert _sunshine_ready(ready) is True


def test_qualification_freshness():
    now = datetime.now(UTC)

    fresh = SimpleNamespace(
        evaluated_at=now
        - QUALIFICATION_MAX_AGE
        + timedelta(seconds=1)
    )

    stale = SimpleNamespace(
        evaluated_at=now
        - QUALIFICATION_MAX_AGE
        - timedelta(seconds=1)
    )

    missing = SimpleNamespace(evaluated_at=None)

    assert qualification_is_fresh(
        fresh,
        now=now,
    ) is True

    assert qualification_is_fresh(
        stale,
        now=now,
    ) is False

    assert qualification_is_fresh(
        missing,
        now=now,
    ) is False
