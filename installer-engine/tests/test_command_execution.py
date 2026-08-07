import subprocess
import sys
from pathlib import Path

import pytest

from kc_installer.engine import (
    CommandExecutionError,
    execute_command,
)


def test_execute_command_captures_output(tmp_path: Path) -> None:
    result = execute_command(
        [
            sys.executable,
            "-c",
            "print('khan-cloud-command-ok')",
        ],
        cwd=tmp_path,
    )

    assert result.command == [
        sys.executable,
        "-c",
        "print('khan-cloud-command-ok')",
    ]
    assert result.returncode == 0
    assert result.stdout.strip() == "khan-cloud-command-ok"
    assert result.stderr == ""


def test_execute_command_does_not_use_shell(
    monkeypatch,
    tmp_path: Path,
) -> None:
    observed: dict = {}

    def fake_run(command, **kwargs):
        observed["command"] = command
        observed["kwargs"] = kwargs

        return subprocess.CompletedProcess(
            command,
            0,
            stdout="ok\n",
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    execute_command(
        ["echo", "hello"],
        cwd=tmp_path,
    )

    assert observed["command"] == ["echo", "hello"]
    assert observed["kwargs"]["shell"] is False
    assert observed["kwargs"]["cwd"] == tmp_path
    assert observed["kwargs"]["capture_output"] is True
    assert observed["kwargs"]["text"] is True
    assert observed["kwargs"]["check"] is False


def test_execute_command_rejects_empty_command(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        ValueError,
        match="Command must not be empty",
    ):
        execute_command([], cwd=tmp_path)


def test_execute_command_raises_structured_error(
    tmp_path: Path,
) -> None:
    with pytest.raises(CommandExecutionError) as exc_info:
        execute_command(
            [
                sys.executable,
                "-c",
                (
                    "import sys; "
                    "print('failure-output', file=sys.stderr); "
                    "sys.exit(7)"
                ),
            ],
            cwd=tmp_path,
        )

    error = exc_info.value

    assert error.result.returncode == 7
    assert "failure-output" in error.result.stderr


def test_execute_command_enforces_timeout(
    tmp_path: Path,
) -> None:
    with pytest.raises(CommandExecutionError) as exc_info:
        execute_command(
            [
                sys.executable,
                "-c",
                "import time; time.sleep(5)",
            ],
            cwd=tmp_path,
            timeout_seconds=0.05,
        )

    assert exc_info.value.result.timed_out is True
