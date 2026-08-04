from app.services.node_service import hash_node_secret, inventory_summary


def test_node_secret_hash_is_stable() -> None:
    assert hash_node_secret("abc") == hash_node_secret("abc")
    assert hash_node_secret("abc") != hash_node_secret("def")


def test_inventory_summary() -> None:
    summary = inventory_summary(
        {
            "cpu": {"model": "Example CPU", "logical_count": 48},
            "memory": {"total_bytes": 34359738368},
            "docker": {"available": True},
            "nvidia": {
                "available": True,
                "gpus": [{"name": "RTX 3080"}],
            },
        }
    )
    assert summary["cpu_model"] == "Example CPU"
    assert summary["cpu_logical_count"] == 48
    assert summary["docker_available"] is True
    assert summary["nvidia_available"] is True
    assert summary["gpu_count"] == 1
