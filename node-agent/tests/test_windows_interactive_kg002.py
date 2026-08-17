from __future__ import annotations

import ast
from pathlib import Path

import pytest

from khan_agent import windows_interactive


def test_non_windows_interactive_launch_is_rejected(monkeypatch):
    monkeypatch.setattr(
        windows_interactive.platform,
        "system",
        lambda: "Linux",
    )

    with pytest.raises(
        windows_interactive.InteractiveSessionError,
        match="only on Windows",
    ):
        windows_interactive.launch_in_active_session(
            ["example.exe", "--test"]
        )


def test_empty_command_is_rejected_before_pywin32(monkeypatch):
    monkeypatch.setattr(
        windows_interactive.platform,
        "system",
        lambda: "Windows",
    )

    with pytest.raises(
        windows_interactive.InteractiveSessionError,
        match="empty",
    ):
        windows_interactive.launch_in_active_session([])


def test_broker_does_not_use_shell_execution():
    source = Path(
        windows_interactive.__file__
    ).read_text(encoding="utf-8")

    assert "shell=True" not in source
    assert "subprocess.list2cmdline" in source
    assert "CreateProcessAsUser" in source
    assert "WTSQueryUserToken" in source
    assert "DuplicateTokenEx" in source


def test_broker_has_no_launcher_specific_coupling():
    source = Path(
        windows_interactive.__file__
    ).read_text(encoding="utf-8").lower()

    tree = ast.parse(source)

    assert "steam.exe" not in source
    assert "epicgameslauncher" not in source
    assert "gog" not in source
    assert "counter-strike" not in source
    assert any(
        isinstance(node, ast.FunctionDef)
        and node.name == "launch_in_active_session"
        for node in ast.walk(tree)
    )


def test_duplicate_token_ex_uses_correct_pywin32_contract():
    source = Path(
        windows_interactive.__file__
    ).read_text(encoding="utf-8")

    tree = ast.parse(source)

    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "DuplicateTokenEx"
    ]

    assert len(calls) == 1

    call = calls[0]

    # pywin32:
    # ExistingToken,
    # ImpersonationLevel,
    # DesiredAccess,
    # TokenType,
    # TokenAttributes=None
    assert len(call.args) == 4
    assert not call.keywords

    assert ast.unparse(call.args[0]) == "user_token"
    assert (
        ast.unparse(call.args[1])
        == "win32security.SecurityIdentification"
    )
    assert (
        ast.unparse(call.args[2])
        == "win32con.MAXIMUM_ALLOWED"
    )
    assert (
        ast.unparse(call.args[3])
        == "win32security.TokenPrimary"
    )

    assert "SECURITY_ATTRIBUTES" not in ast.unparse(call)
