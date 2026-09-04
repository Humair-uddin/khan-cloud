from __future__ import annotations

import json
import subprocess

import pytest

from khan_agent import vdd_activation as activation


def cp(stdout="", stderr="", returncode=0):
    return subprocess.CompletedProcess(
        args=[],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


def health_json(status="OK", problem=0):
    return json.dumps(
        {
            "instance_id": r"ROOT\DISPLAY\0000",
            "status": status,
            "problem_code": problem,
            "friendly_name": "Khan Virtual Display",
        }
    )


def test_activation_verifies_healthy_vdd_without_restart(
    monkeypatch,
):
    monkeypatch.setattr(
        activation.platform,
        "system",
        lambda: "Windows",
    )

    commands = []

    def runner(argv, **kwargs):
        commands.append(argv)
        return cp(health_json())

    result = activation.activate_vdd_policy(
        runner=runner,
    )

    joined = "\n".join(
        " ".join(map(str, command))
        for command in commands
    )

    assert r"ROOT\DISPLAY\0000" in joined
    assert "pnputil.exe" not in joined
    assert "/restart-device" not in joined
    assert "Start-Process" not in joined
    assert "/reboot" not in joined.lower()
    assert "shutdown" not in joined.lower()

    assert len(commands) == 1
    assert result["healthy"] is True
    assert result["activation_required"] is False
    assert result["reboot_required"] is False
    assert result["restart_elapsed_ms"] is None
    assert (
        result["activation_method"]
        == "health-verification-only"
    )
    assert (
        result["reason"]
        == "healthy-vdd-no-pnp-restart"
    )


def test_non_windows_activation_fails_closed(monkeypatch):
    monkeypatch.setattr(
        activation.platform,
        "system",
        lambda: "Linux",
    )

    with pytest.raises(
        activation.VddActivationError
    ):
        activation.query_vdd_health()


def test_unhealthy_device_refuses_restart(monkeypatch):
    monkeypatch.setattr(
        activation.platform,
        "system",
        lambda: "Windows",
    )

    calls = []

    def runner(argv, **kwargs):
        calls.append(argv)
        return cp(
            health_json(
                status="Error",
                problem=43,
            )
        )

    with pytest.raises(
        activation.VddActivationError
    ):
        activation.activate_vdd_policy(
            runner=runner
        )

    text = "\n".join(
        " ".join(map(str, c))
        for c in calls
    )

    assert "Start-Process" not in text


def test_activation_does_not_enter_restart_failure_path(
    monkeypatch,
):
    monkeypatch.setattr(
        activation.platform,
        "system",
        lambda: "Windows",
    )

    calls = []

    def runner(argv, **kwargs):
        calls.append(argv)

        if len(calls) > 1:
            raise AssertionError(
                "healthy activation attempted a second command"
            )

        return cp(health_json())

    result = activation.activate_vdd_policy(
        runner=runner,
    )

    assert len(calls) == 1
    assert result["healthy"] is True
    assert result["activation_required"] is False
    assert (
        result["activation_method"]
        == "health-verification-only"
    )


def test_health_model_requires_ok_and_problem_zero():
    assert activation.VddDeviceHealth(
        r"ROOT\DISPLAY\0000",
        "OK",
        0,
        "Khan Virtual Display",
    ).healthy

    assert not activation.VddDeviceHealth(
        r"ROOT\DISPLAY\0000",
        "OK",
        43,
        "Khan Virtual Display",
    ).healthy

    assert not activation.VddDeviceHealth(
        r"ROOT\DISPLAY\0000",
        "Error",
        0,
        "Khan Virtual Display",
    ).healthy


def test_activation_targets_only_khan_vdd():
    assert (
        activation.VDD_INSTANCE_ID
        == r"ROOT\DISPLAY\0000"
    )


def test_live_activation_available_tracks_platform(
    monkeypatch,
):
    monkeypatch.setattr(
        activation.platform,
        "system",
        lambda: "Windows",
    )

    assert (
        activation.live_activation_available()
        is True
    )

    monkeypatch.setattr(
        activation.platform,
        "system",
        lambda: "Linux",
    )

    assert (
        activation.live_activation_available()
        is False
    )
