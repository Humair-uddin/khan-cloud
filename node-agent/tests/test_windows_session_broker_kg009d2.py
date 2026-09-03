import pytest

from khan_agent import windows_session_broker as broker


def test_non_windows_is_fail_closed(monkeypatch):
    monkeypatch.setattr(broker.platform, "system", lambda: "Linux")

    session = broker.discover_interactive_session()

    assert session.available is False
    assert session.session_id == 0
    assert session.source == "unsupported_platform"
    assert session.managed is False


def test_require_rejects_unavailable(monkeypatch):
    monkeypatch.setattr(
        broker,
        "discover_interactive_session",
        lambda: broker.InteractiveSession(
            session_id=0,
            available=False,
            source="no_active_console",
        ),
    )

    with pytest.raises(
        broker.WindowsSessionBrokerError,
        match="No usable Windows interactive session",
    ):
        broker.require_interactive_session()


def test_require_accepts_exact_session(monkeypatch):
    monkeypatch.setattr(
        broker,
        "discover_interactive_session",
        lambda: broker.InteractiveSession(
            session_id=7,
            available=True,
            source="active_console",
        ),
    )

    session = broker.require_interactive_session(
        expected_session_id=7,
    )

    assert session.session_id == 7
    assert session.available is True


def test_require_rejects_session_race(monkeypatch):
    monkeypatch.setattr(
        broker,
        "discover_interactive_session",
        lambda: broker.InteractiveSession(
            session_id=8,
            available=True,
            source="active_console",
        ),
    )

    with pytest.raises(
        broker.WindowsSessionBrokerError,
        match="session changed before launch",
    ):
        broker.require_interactive_session(
            expected_session_id=7,
        )
