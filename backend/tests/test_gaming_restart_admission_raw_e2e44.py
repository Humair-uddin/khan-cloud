from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def source(path):
    return (ROOT / path).read_text()


def test_restart_admission_precedes_billing_reopen():
    text = source("app/services/gaming_service.py")
    section = text.split(
        "def queue_gaming_action(", 1
    )[1].split(
        "def ", 1
    )[0]

    start = section.split('if action == "start":', 1)[1]

    assert "select(NodeCapacity)" in start
    assert ".with_for_update()" in start
    assert "select(Node)" in start
    assert 'node.lifecycle_state != "approved"' in start
    assert "not node.gaming_accepting_work" in start
    assert "node.gaming_admission_auto_blocked" in start

    assert start.index(
        "Gaming host is not accepting session starts."
    ) < start.index("reopen_gaming_billing(")


def test_availability_uses_capacity_admission_lock():
    text = source("app/api/v1/nodes.py")
    section = text.split(
        "def set_gaming_availability(", 1
    )[1].split(
        "@router.", 1
    )[0]

    assert "select(NodeCapacity)" in section
    assert ".with_for_update()" in section
    assert "select(Node)" in section

    assert section.index(
        "select(NodeCapacity)"
    ) < section.index(
        "node.gaming_accepting_work = payload.accepting_work"
    )


def test_stop_and_terminate_remain_separate():
    text = source("app/services/gaming_service.py")
    section = text.split(
        "def queue_gaming_action(", 1
    )[1].split(
        "def ", 1
    )[0]

    assert 'if action == "start":' in section
    assert "prepare_connection_shutdown" in section
    assert 'if action == "terminate":' in section
