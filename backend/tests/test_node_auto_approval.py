from pathlib import Path


def test_scoped_profile_can_authorize_auto_approval():
    root = Path(__file__).resolve().parents[1]
    api = (root / "app" / "api" / "v1" / "nodes.py").read_text()
    service = (root / "app" / "services" / "node_service.py").read_text()
    assert 'get("auto_approve_node")' in api
    assert "auto_approve_enrolled_node" in api
    assert 'action="node.auto_approved"' in service
