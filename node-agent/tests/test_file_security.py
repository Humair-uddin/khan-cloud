import os
from pathlib import Path

from khan_agent import file_security


def test_posix_private_file_uses_mode_0600(monkeypatch, tmp_path):
    if os.name == "nt":
        return

    path = tmp_path / "secret.json"
    path.write_text("secret")

    monkeypatch.setattr(file_security.platform, "system", lambda: "Linux")

    file_security.secure_private_file(path)

    assert (path.stat().st_mode & 0o777) == 0o600


def test_windows_private_file_uses_icacls(monkeypatch, tmp_path):
    path = tmp_path / "secret.json"
    path.write_text("secret")

    monkeypatch.setattr(file_security.platform, "system", lambda: "Windows")

    commands = []

    def fake_run(command, **kwargs):
        commands.append(command)

        class Result:
            returncode = 0
            stdout = ""
            stderr = ""

        return Result()

    monkeypatch.setattr(file_security.subprocess, "run", fake_run)

    file_security.secure_private_file(path)

    assert len(commands) == 1

    command = commands[0]
    assert command[0].lower() == "icacls"
    assert str(path) in command
    assert "/inheritance:r" in command
    assert "/grant:r" in command
    assert "*S-1-5-18:(F)" in command
    assert "*S-1-5-32-544:(F)" in command

    grant_index = command.index("/grant:r")
    grants = command[grant_index + 1:]

    assert grants == [
        "*S-1-5-18:(F)",
        "*S-1-5-32-544:(F)",
    ]



def test_windows_private_file_fails_closed_when_acl_fails(monkeypatch, tmp_path):
    path = tmp_path / "secret.json"
    path.write_text("secret")

    monkeypatch.setattr(file_security.platform, "system", lambda: "Windows")

    def fake_run(command, **kwargs):
        class Result:
            returncode = 5
            stdout = ""
            stderr = "Access is denied."

        return Result()

    monkeypatch.setattr(file_security.subprocess, "run", fake_run)

    try:
        file_security.secure_private_file(path)
    except RuntimeError as exc:
        assert "private file permissions" in str(exc).lower()
    else:
        raise AssertionError("Windows ACL failure must fail closed")
