from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_version_endpoint() -> None:
    response = client.get("/version")
    assert response.status_code == 200
    payload = response.json()
    assert payload["component"] == "control-plane"
    assert payload["api_version"] == "v1"
    assert payload["product"]


def test_ready_endpoint_has_stable_contract() -> None:
    response = client.get("/ready")
    assert response.status_code in {200, 503}
    payload = response.json()
    assert isinstance(payload["ready"], bool)
    assert payload["database"] in {"connected", "disconnected"}
    assert payload["version"]
    assert payload["environment"]
    assert payload["checked_at"]


def test_openapi_documents_foundation_endpoints() -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/ready" in paths
    assert "/version" in paths


def test_existing_health_endpoint_is_preserved() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert "status" in payload
    assert "database" in payload
    assert "version" in payload
