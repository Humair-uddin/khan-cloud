from khan_agent import gaming_inventory


def test_non_windows_interactive_session_is_unavailable(monkeypatch):
    monkeypatch.setattr(
        gaming_inventory.platform,
        "system",
        lambda: "Linux",
    )

    assert gaming_inventory.collect_interactive_session() == {
        "available": False,
        "session_id": None,
        "username": "",
    }


def test_gaming_inventory_contains_interactive_session(monkeypatch):
    monkeypatch.setattr(
        gaming_inventory,
        "collect_steam_inventory",
        lambda: {
            "installed": True,
            "roots": [],
            "libraries": [],
            "games": [],
        },
    )
    monkeypatch.setattr(
        gaming_inventory,
        "locate_sunshine",
        lambda: None,
    )
    monkeypatch.setattr(
        gaming_inventory,
        "collect_interactive_session",
        lambda: {
            "available": True,
            "session_id": 1,
            "username": "TEST\\KC-01",
        },
    )

    inventory = gaming_inventory.collect_gaming_inventory()

    assert inventory["interactive_session"]["available"] is True
    assert inventory["interactive_session"]["session_id"] == 1


def test_windows_interactive_session_detects_console_explorer(
    monkeypatch,
):
    captured = {}

    class Result:
        returncode = 0
        stdout = "1|DESKTOP-4ROCVUH\\KC-01\n"
        stderr = ""

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return Result()

    monkeypatch.setattr(
        gaming_inventory.platform,
        "system",
        lambda: "Windows",
    )

    monkeypatch.setattr(
        gaming_inventory.subprocess,
        "run",
        fake_run,
    )

    result = (
        gaming_inventory.collect_interactive_session()
    )

    assert result == {
        "available": True,
        "session_id": 1,
        "username": "DESKTOP-4ROCVUH\\KC-01",
    }

    command = captured["command"]

    assert command[:4] == [
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-Command",
    ]

    script = command[4]

    assert (
        "Where-Object { $_.Name -eq 'explorer.exe' }"
        in script
    )

    assert "[char]92" in script
    assert captured["kwargs"]["shell"] is False if (
        "shell" in captured["kwargs"]
    ) else True
