import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def test_upstreams_are_pinned():
    data = load("upstream/provenance.json")
    assert data["contract_version"] == "kg008k-v1"
    assert len(data["upstreams"]) == 2

    for upstream in data["upstreams"]:
        commit = upstream["commit"]
        assert len(commit) == 40
        assert all(c in "0123456789abcdef" for c in commit.lower())


def test_customer_profiles():
    data = load("profiles/display-modes.json")

    profiles = data["customer_profiles"]

    assert profiles["standard"]["preferred"] == {
        "width": 1920,
        "height": 1080,
        "refresh_hz": 60,
    }

    assert profiles["high"]["preferred"] == {
        "width": 2560,
        "height": 1440,
        "refresh_hz": 120,
    }

    assert profiles["ultra"]["preferred"] == {
        "width": 3840,
        "height": 2160,
        "refresh_hz": 60,
    }


def test_adaptive_emergency_mode_exists():
    modes = load("profiles/display-modes.json")["adaptive_modes"]

    assert {
        "width": 1280,
        "height": 720,
        "refresh_hz": 30,
    } in modes


def test_control_protocol_operations():
    operations = load("control/protocol.json")["operations"]

    assert set(operations) == {
        "get_status",
        "list_modes",
        "set_mode",
        "enable_monitor",
        "disable_monitor",
    }


def test_vdd_is_image_build_khan_artifact():
    artifact = load("installer/artifact-template.json")

    assert artifact["source"]["type"] == "khan_artifact"
    assert artifact["stage"] == "image_build"
