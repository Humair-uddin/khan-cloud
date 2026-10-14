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

def test_session_username_retries_transient_wts_failure(
    monkeypatch,
):
    calls = {"count": 0}

    class FakeTs:
        WTSUserName = 5
        WTSDomainName = 7

        @staticmethod
        def WTSQuerySessionInformation(
            server,
            session_id,
            info_class,
        ):
            if info_class == FakeTs.WTSUserName:
                calls["count"] += 1

                if calls["count"] == 1:
                    raise RuntimeError("transient WTS failure")

                return "KhanGaming"

            return "KC-HOST"

    monkeypatch.setattr(
        broker.time,
        "sleep",
        lambda _seconds: None,
    )

    username = broker._session_username_with_retry(
        FakeTs,
        4,
    )

    assert username == "KC-HOST\\KhanGaming"
    assert calls["count"] == 2


def test_session_username_retries_transient_blank_identity(
    monkeypatch,
):
    calls = {"count": 0}

    class FakeTs:
        WTSUserName = 5
        WTSDomainName = 7

        @staticmethod
        def WTSQuerySessionInformation(
            server,
            session_id,
            info_class,
        ):
            if info_class == FakeTs.WTSUserName:
                calls["count"] += 1

                if calls["count"] == 1:
                    return ""

                return "KhanGaming"

            return "KC-HOST"

    monkeypatch.setattr(
        broker.time,
        "sleep",
        lambda _seconds: None,
    )

    username = broker._session_username_with_retry(
        FakeTs,
        4,
    )

    assert username == "KC-HOST\\KhanGaming"
    assert calls["count"] == 2


def test_session_username_persistent_blank_fails_explicitly(
    monkeypatch,
):
    calls = {"count": 0}

    class FakeTs:
        WTSUserName = 5
        WTSDomainName = 7

        @staticmethod
        def WTSQuerySessionInformation(
            server,
            session_id,
            info_class,
        ):
            if info_class == FakeTs.WTSUserName:
                calls["count"] += 1
                return ""

            return "KC-HOST"

    monkeypatch.setattr(
        broker.time,
        "sleep",
        lambda _seconds: None,
    )

    with pytest.raises(
        broker.WindowsSessionBrokerError,
        match=(
            "Unable to query Windows interactive-session "
            "identity after 3 attempts"
        ),
    ):
        broker._session_username_with_retry(
            FakeTs,
            4,
        )

    assert calls["count"] == 3


def test_session_username_fails_explicitly_after_retry_budget(
    monkeypatch,
):
    calls = {"count": 0}

    class FakeTs:
        WTSUserName = 5
        WTSDomainName = 7

        @staticmethod
        def WTSQuerySessionInformation(
            server,
            session_id,
            info_class,
        ):
            calls["count"] += 1
            raise RuntimeError("WTS unavailable")

    monkeypatch.setattr(
        broker.time,
        "sleep",
        lambda _seconds: None,
    )

    with pytest.raises(
        broker.WindowsSessionBrokerError,
        match=(
            "Unable to query Windows interactive-session "
            "identity after 3 attempts"
        ),
    ):
        broker._session_username_with_retry(
            FakeTs,
            4,
        )

    assert calls["count"] == 3


def test_foreign_console_is_not_retried_into_managed_session(
    monkeypatch,
    tmp_path,
):
    import json

    state = tmp_path / "session-broker.json"
    state.write_text(
        json.dumps(
            {
                "mode": "managed_autologon",
                "managed": True,
                "username": "KhanGaming",
            }
        ),
        encoding="utf-8",
    )

    calls = {"count": 0}

    class FakeTs:
        WTSUserName = 5
        WTSDomainName = 7

        @staticmethod
        def WTSGetActiveConsoleSessionId():
            return 4

        @staticmethod
        def WTSQuerySessionInformation(
            server,
            session_id,
            info_class,
        ):
            if info_class == FakeTs.WTSUserName:
                calls["count"] += 1
                return "ForeignUser"

            return "KC-HOST"

    monkeypatch.setattr(
        broker.platform,
        "system",
        lambda: "Windows",
    )

    import sys

    monkeypatch.setitem(
        sys.modules,
        "win32ts",
        FakeTs,
    )

    session = broker.discover_interactive_session(
        state_path=state,
    )

    assert session.available is True
    assert session.managed is False
    assert session.source == "active_console"
    assert session.username == "KC-HOST\\ForeignUser"
    assert calls["count"] == 1
