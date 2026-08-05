from types import SimpleNamespace
from app.services.node_service import normalized_capabilities,sync_legacy_status

def test_capabilities_are_normalized():
    c=normalized_capabilities({"gaming":True},{"docker":{"available":True},"nvidia":{"available":True,"gpus":[{"name":"GPU"}]}})
    assert c["gaming"] is True
    assert c["docker"] is True
    assert c["gpu"] is True

def test_pending_online_legacy_status():
    n=SimpleNamespace(lifecycle_state="pending_approval",connectivity_state="online",status="")
    sync_legacy_status(n)
    assert n.status=="online"

def test_retired_stays_retired():
    n=SimpleNamespace(lifecycle_state="retired",connectivity_state="online",status="")
    sync_legacy_status(n)
    assert n.status=="retired"
