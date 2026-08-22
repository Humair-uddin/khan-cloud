from pathlib import Path


def test_node_provisioning_routes_present():
    source = Path("app/api/v1/nodes.py").read_text()
    assert '@router.post("/provisioning-events"' in source
    assert '@router.get("/desired-state"' in source
    assert 'inventory["provisioning"]' in source


def test_provisioning_schema_contains_dashboard_progress_contract():
    source = Path("app/schemas/provisioning.py").read_text()
    for field in (
        "progress", "downloaded_bytes", "total_bytes", "bytes_per_second",
        "eta_seconds", "last_checkpoint", "retry_count", "desired_image_version",
    ):
        assert field in source


def test_desired_state_exposes_image_build_plan():
    source = Path("app/api/v1/nodes.py").read_text()
    schema = Path("app/schemas/provisioning.py").read_text()
    assert 'image_build_plan=dict(policy.get("image_build_plan") or {})' in source
    assert "image_build_plan:" in schema
