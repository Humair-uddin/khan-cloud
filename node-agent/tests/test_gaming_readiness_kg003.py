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
        "managed": False,
        "source": "unsupported_platform",
        "broker_mode": "existing",
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


def test_windows_interactive_session_detects_console_session(
    monkeypatch,
):
    from khan_agent.windows_session_broker import InteractiveSession

    monkeypatch.setattr(
        gaming_inventory.platform,
        "system",
        lambda: "Windows",
    )

    monkeypatch.setattr(
        gaming_inventory,
        "discover_interactive_session",
        lambda: InteractiveSession(
            session_id=1,
            available=True,
            source="active_console",
            managed=False,
            username="DESKTOP-4ROCVUH\\KC-01",
            broker_mode="existing",
        ),
    )

    result = gaming_inventory.collect_interactive_session()

    assert result == {
        "available": True,
        "session_id": 1,
        "username": "DESKTOP-4ROCVUH\\KC-01",
        "managed": False,
        "source": "active_console",
        "broker_mode": "existing",
    }
