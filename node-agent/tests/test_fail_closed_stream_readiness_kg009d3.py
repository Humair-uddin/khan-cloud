from __future__ import annotations

import inspect

from khan_agent import gaming_runtime


def _source(function):
    return inspect.getsource(function)


def test_running_create_demotes_stale_readiness_on_failure():
    text = _source(gaming_runtime.create_session)

    start = text.index(
        'if existing.get("status") == "running":'
    )
    end = text.index(
        "_write_state(state_file, existing)",
        start,
    )
    block = text[start:end]

    assert 'existing.pop(' in block
    assert '"stream_readiness"' in block
    assert '"readiness_pending"' in block


def test_running_start_demotes_stale_readiness_on_failure():
    text = _source(
        gaming_runtime.change_session_state
    )

    start = text.index(
        'if state.get("status") == "running":'
    )
    end = text.index(
        "game_slug = str(",
        start,
    )
    block = text[start:end]

    assert 'state.pop(' in block
    assert '"stream_readiness"' in block
    assert '"readiness_pending"' in block


def test_restart_readiness_failure_terminates_and_restores_stopped():
    text = _source(
        gaming_runtime.change_session_state
    )

    start = text.index(
        "runtime_ownership = ("
    )
    block = text[start:]

    readiness = block.index(
        "readiness = _verify_stream_readiness("
    )
    termination = block.index(
        "terminate_runtime_ownership(",
        readiness,
    )
    stopped = block.index(
        'state["status"] = "stopped"',
        termination,
    )
    no_process = block.index(
        "no_process_ownership()",
        stopped,
    )

    assert readiness < termination < stopped < no_process


def test_pair_requires_verified_stream_readiness():
    text = _source(
        gaming_runtime.pair_connection
    )

    assert (
        'state.get("runtime_stage") != "stream_ready"'
        in text
    )
    assert (
        'not bool(readiness.get("verified"))'
        in text
    )
    assert (
        text.index(
            'state.get("runtime_stage") != "stream_ready"'
        )
        < text.index("pair_client(")
    )


def test_failed_launch_cleanup_requires_verified_termination():
    text = _source(
        gaming_runtime._cleanup_failed_launch
    )

    assert "terminate_runtime_ownership(" in text
    assert '"termination_verified"' in text
    assert '"ownership_boundary_verified"' in text
    assert "remaining == 0" in text
    assert '"verified": verified' in text


def test_restart_preserves_cleanup_required_when_unverified():
    text = _source(
        gaming_runtime.change_session_state
    )

    start = text.rindex(
        "readiness = _verify_stream_readiness("
    )
    block = text[start:]

    assert "_cleanup_failed_launch(" in block
    assert 'if cleanup["verified"]:' in block
    assert '"cleanup_required"' in block
    assert '"readiness_failure"' in block
    assert 'state["cleanup"] = cleanup' in block
    assert (
        'state["runtime_ownership"] = ('
        in block
    )


def test_verified_restart_cleanup_restores_stopped():
    text = _source(
        gaming_runtime.change_session_state
    )

    start = text.rindex(
        "readiness = _verify_stream_readiness("
    )
    block = text[start:]

    verified = block.index(
        'if cleanup["verified"]:'
    )
    stopped = block.index(
        'state["status"] = "stopped"',
        verified,
    )
    no_process = block.index(
        "no_process_ownership()",
        stopped,
    )

    assert verified < stopped < no_process


def _owned_runtime():
    return {
        "schema_version": 2,
        "ownership_type": "windows_job_object",
        "job_name": "Global\\KhanCloudGaming_test",
        "root_pid": 4242,
        "supervisor_pid": 3131,
        "interactive_session_id": 1,
        "boundary_established": True,
    }


def test_cleanup_helper_accepts_only_verified_clean_termination(
    monkeypatch,
):
    ownership = _owned_runtime()

    monkeypatch.setattr(
        gaming_runtime,
        "terminate_runtime_ownership",
        lambda candidate: {
            "ownership_type": "windows_job_object",
            "job_name": candidate["job_name"],
            "ownership_boundary_verified": True,
            "termination_verified": True,
            "owned_process_count_remaining": 0,
        },
    )

    result = gaming_runtime._cleanup_failed_launch(
        ownership
    )

    assert result["verified"] is True
    assert result["error"] is None
    assert result["runtime_ownership"] == ownership
    assert (
        result["termination_proof"][
            "termination_verified"
        ]
        is True
    )


def test_cleanup_helper_rejects_unverified_termination(
    monkeypatch,
):
    ownership = _owned_runtime()

    monkeypatch.setattr(
        gaming_runtime,
        "terminate_runtime_ownership",
        lambda candidate: {
            "ownership_type": "windows_job_object",
            "job_name": candidate["job_name"],
            "ownership_boundary_verified": True,
            "termination_verified": False,
            "owned_process_count_remaining": 1,
        },
    )

    result = gaming_runtime._cleanup_failed_launch(
        ownership
    )

    assert result["verified"] is False
    assert (
        result["error"]
        == "runtime_termination_not_verified"
    )
    assert result["runtime_ownership"] == ownership
    assert (
        result["termination_proof"][
            "termination_verified"
        ]
        is False
    )
    assert (
        result["termination_proof"][
            "owned_process_count_remaining"
        ]
        == 1
    )


def test_cleanup_helper_preserves_termination_exception(
    monkeypatch,
):
    ownership = _owned_runtime()

    def fail(candidate):
        assert candidate == ownership
        raise gaming_runtime.RuntimeOwnershipError(
            "synthetic termination failure"
        )

    monkeypatch.setattr(
        gaming_runtime,
        "terminate_runtime_ownership",
        fail,
    )

    result = gaming_runtime._cleanup_failed_launch(
        ownership
    )

    assert result["verified"] is False
    assert result["termination_proof"] is None
    assert result["runtime_ownership"] == ownership
    assert (
        "synthetic termination failure"
        in result["error"]
    )


def test_create_cleanup_contract_preserves_recovery_evidence():
    text = _source(gaming_runtime.create_session)

    readiness = text.index(
        "readiness = _verify_stream_readiness("
    )
    block = text[readiness:]

    assert "_cleanup_failed_launch(" in block
    assert 'if cleanup["verified"]:' in block

    # Verified cleanup removes the incomplete create state.
    verified = block.index(
        'if cleanup["verified"]:'
    )
    unlink = block.index(
        "state_file.unlink()",
        verified,
    )

    # Unverified cleanup persists a durable recovery state.
    cleanup_required = block.index(
        '"cleanup_required"',
        unlink,
    )
    write_state = block.index(
        "_write_state(",
        cleanup_required,
    )

    assert (
        verified
        < unlink
        < cleanup_required
        < write_state
    )

    assert '"readiness_failure"' in block
    assert '"cleanup"' in block
    assert '"launch_info"' in block
    assert '"runtime_ownership"' in block


def test_restart_cleanup_contract_is_fail_closed():
    text = _source(
        gaming_runtime.change_session_state
    )

    start = text.rindex(
        "readiness = _verify_stream_readiness("
    )
    block = text[start:]

    assert "_cleanup_failed_launch(" in block

    verified = block.index(
        'if cleanup["verified"]:'
    )

    stopped = block.index(
        'state["status"] = "stopped"',
        verified,
    )

    no_process = block.index(
        "no_process_ownership()",
        stopped,
    )

    unverified = block.index(
        '"cleanup_required"',
        no_process,
    )

    write_state = block.index(
        "_write_state(",
        unverified,
    )

    assert (
        verified
        < stopped
        < no_process
        < unverified
        < write_state
    )

    assert '"readiness_failure"' in block
    assert 'state["cleanup"] = cleanup' in block

