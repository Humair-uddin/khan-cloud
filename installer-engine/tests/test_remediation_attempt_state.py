from pathlib import Path

import pytest

from kc_installer.state import InstallerState


def make_state(tmp_path: Path) -> tuple[InstallerState, str]:
    state = InstallerState(tmp_path / "installer.db")

    transaction_id = state.begin(
        feature_pack_id="FP-ATTEMPT",
        feature_pack_version="1.0.0",
        package_path=tmp_path / "package",
        target_path=tmp_path / "target",
        backup_path=tmp_path / "backup",
        dry_run=False,
    )

    state.record_remediation_plan(
        transaction_id,
        [
            {
                "dependency_name": "Docker",
                "action_type": "command",
                "command": [
                    "apt-get",
                    "install",
                    "-y",
                    "docker.io",
                ],
                "description": "Install Docker.",
                "eligible": True,
                "policy_reason": "eligible",
            }
        ],
    )

    return state, transaction_id


def test_remediation_execution_attempt_is_persisted(
    tmp_path: Path,
) -> None:
    state, transaction_id = make_state(tmp_path)

    attempt_id = state.begin_remediation_attempt(
        transaction_id,
        0,
    )

    state.finish_remediation_attempt(
        attempt_id,
        status="success",
        return_code=0,
        timed_out=False,
        stdout="installed\n",
        stderr="",
        verified=True,
    )

    attempts = state.remediation_attempts(transaction_id)

    assert len(attempts) == 1

    attempt = attempts[0]

    assert attempt["id"] == attempt_id
    assert attempt["dependency_name"] == "Docker"
    assert attempt["position"] == 0
    assert attempt["attempt_number"] == 1
    assert attempt["status"] == "success"
    assert attempt["return_code"] == 0
    assert attempt["timed_out"] is False
    assert attempt["stdout"] == "installed\n"
    assert attempt["stderr"] == ""
    assert attempt["verified"] is True
    assert attempt["error_message"] == ""
    assert attempt["completed_at"] is not None

    journal = state.journal(transaction_id)

    execution_entries = [
        item
        for item in journal
        if item["stage"] == "remediation_execution"
    ]

    assert [item["status"] for item in execution_entries] == [
        "started",
        "success",
    ]


def test_multiple_attempts_preserve_history(
    tmp_path: Path,
) -> None:
    state, transaction_id = make_state(tmp_path)

    first = state.begin_remediation_attempt(
        transaction_id,
        0,
    )

    state.finish_remediation_attempt(
        first,
        status="failed",
        return_code=7,
        stderr="first failure",
        verified=False,
        error_message="command failed",
    )

    second = state.begin_remediation_attempt(
        transaction_id,
        0,
    )

    state.finish_remediation_attempt(
        second,
        status="success",
        return_code=0,
        stdout="second attempt succeeded",
        verified=True,
    )

    attempts = state.remediation_attempts(transaction_id)

    assert [item["attempt_number"] for item in attempts] == [1, 2]
    assert [item["status"] for item in attempts] == [
        "failed",
        "success",
    ]

    assert attempts[0]["stderr"] == "first failure"
    assert attempts[1]["verified"] is True


def test_unknown_remediation_position_is_rejected(
    tmp_path: Path,
) -> None:
    state, transaction_id = make_state(tmp_path)

    with pytest.raises(
        ValueError,
        match="Remediation action not found",
    ):
        state.begin_remediation_attempt(
            transaction_id,
            99,
        )


def test_plan_cannot_be_replaced_after_execution_attempt(
    tmp_path: Path,
) -> None:
    state, transaction_id = make_state(tmp_path)

    state.begin_remediation_attempt(
        transaction_id,
        0,
    )

    with pytest.raises(
        ValueError,
        match="Cannot replace remediation plan",
    ):
        state.record_remediation_plan(
            transaction_id,
            [],
        )
