from app.main import app

def test_governance_routes_are_registered():
    paths={r.path for r in app.routes if hasattr(r,"path")}
    expected={
      "/api/v1/nodes/{node_id}/approve",
      "/api/v1/nodes/{node_id}/reject",
      "/api/v1/nodes/{node_id}/disable",
      "/api/v1/nodes/{node_id}/enable",
      "/api/v1/nodes/{node_id}/maintenance",
      "/api/v1/nodes/{node_id}/retire",
      "/api/v1/audit",
    }
    assert expected <= paths
