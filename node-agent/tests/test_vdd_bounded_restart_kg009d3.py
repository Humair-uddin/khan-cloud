from __future__ import annotations

import subprocess

import pytest

from khan_agent import vdd_activation as activation


def _healthy() -> activation.VddDeviceHealth:
    return activation.VddDeviceHealth(
        instance_id=activation.VDD_INSTANCE_ID,
        status="OK",
        problem_code=0,
        friendly_name=activation.VDD_FRIENDLY_NAME,
    )


def test_d3_restart_invokes_pnputil_directly(monkeypatch):
    monkeypatch.setattr(
        activation,
        "live_activation_available",
        lambda: True,
    )
    monkeypatch.setattr(
        activation,
        "query_vdd_health",
        lambda **kwargs: _healthy(),
    )

    calls = []

    def runner(command, **kwargs):
        calls.append((command, kwargs))

        return subprocess.CompletedProcess(
            command,
            0,
            stdout="Microsoft PnP Utility\n",
            stderr="",
        )

    result = activation.restart_vdd_device(
        runner=runner,
        timeout=17.0,
    )

    assert len(calls) == 1

    command, kwargs = calls[0]

    assert command == [
        "pnputil.exe",
        "/restart-device",
        activation.VDD_INSTANCE_ID,
    ]

    assert "powershell.exe" not in command
    assert kwargs["check"] is False
    assert kwargs["capture_output"] is True
    assert kwargs["text"] is True
    assert kwargs["timeout"] == 17.0

    assert result["instance_id"] == activation.VDD_INSTANCE_ID
    assert result["exit_code"] == 0
    assert result["elapsed_ms"] >= 0


def test_d3_restart_timeout_fails_closed(monkeypatch):
    monkeypatch.setattr(
        activation,
        "live_activation_available",
        lambda: True,
    )
    monkeypatch.setattr(
        activation,
        "query_vdd_health",
        lambda **kwargs: _healthy(),
    )

    def runner(command, **kwargs):
        raise subprocess.TimeoutExpired(
            command,
            kwargs["timeout"],
        )

    with pytest.raises(
        activation.VddActivationError,
        match="restart timed out",
    ):
        activation.restart_vdd_device(
            runner=runner,
            timeout=3.0,
        )


def test_d3_restart_nonzero_exit_fails_closed(monkeypatch):
    monkeypatch.setattr(
        activation,
        "live_activation_available",
        lambda: True,
    )
    monkeypatch.setattr(
        activation,
        "query_vdd_health",
        lambda **kwargs: _healthy(),
    )

    def runner(command, **kwargs):
        return subprocess.CompletedProcess(
            command,
            5,
            stdout="",
            stderr="restart rejected",
        )

    with pytest.raises(
        activation.VddActivationError,
        match="restart rejected",
    ):
        activation.restart_vdd_device(
            runner=runner,
        )


def test_d3_restart_refuses_unhealthy_device(monkeypatch):
    monkeypatch.setattr(
        activation,
        "live_activation_available",
        lambda: True,
    )
    monkeypatch.setattr(
        activation,
        "query_vdd_health",
        lambda **kwargs: activation.VddDeviceHealth(
            instance_id=activation.VDD_INSTANCE_ID,
            status="Error",
            problem_code=31,
            friendly_name=activation.VDD_FRIENDLY_NAME,
        ),
    )

    called = False

    def runner(command, **kwargs):
        nonlocal called
        called = True
        raise AssertionError(
            "pnputil must not execute for unhealthy VDD"
        )

    with pytest.raises(
        activation.VddActivationError,
        match="unhealthy",
    ):
        activation.restart_vdd_device(
            runner=runner,
        )

    assert called is False


def test_d3_activation_never_restarts_healthy_vdd(
    monkeypatch,
):
    monkeypatch.setattr(
        activation,
        "query_vdd_health",
        lambda **kwargs: _healthy(),
    )

    def forbidden_restart(**kwargs):
        raise AssertionError(
            "normal D3 activation must not restart healthy VDD"
        )

    def forbidden_wait(**kwargs):
        raise AssertionError(
            "normal D3 activation must not enter restart recovery"
        )

    monkeypatch.setattr(
        activation,
        "restart_vdd_device",
        forbidden_restart,
    )
    monkeypatch.setattr(
        activation,
        "wait_for_vdd_health",
        forbidden_wait,
    )

    result = activation.activate_vdd_policy()

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


