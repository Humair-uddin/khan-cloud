import json
from uuid import uuid4

import pytest

from khan_agent import gaming_runtime


def generation(session_id):
    return {
        "reservation_id": str(uuid4()),
        "node_id": str(uuid4()),
        "gpu_uuid": "GPU-test",
        "runtime_id": f"kc-gaming-{session_id}",
    }


def fence(identity):
    return {
        **identity,
        "runtime_started_at": "2026-10-15T10:00:00+00:00",
        "billing_generation": str(uuid4()),
    }


def runtime_state(tmp_path, session_id, identity):
    sessions = tmp_path / "sessions"
    sessions.mkdir(parents=True, exist_ok=True)

    path = sessions / f"kc-gaming-{session_id}.json"
    path.write_text(
        json.dumps({
            "schema_version": 2,
            "session_id": str(session_id),
            "runtime_id": identity["runtime_id"],
            "gpu_uuid": identity["gpu_uuid"],
            "status": "stopped",
            "runtime_generation": identity,
            "runtime_ownership": {
                "schema_version": 2,
                "ownership_type": "terminated",
                "runtime_id": identity["runtime_id"],
                "ownership_boundary_verified": True,
                "termination_verified": True,
                "owned_process_count": 0,
                "owned_process_count_remaining": 0,
                "clean": True,
            },
            "paired_clients": [],
        }),
        encoding="utf-8",
    )
    return path


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "malformed",
        "reservation",
        "node",
        "gpu",
        "runtime",
    ],
)
def test_delete_rejects_invalid_generation_without_cleanup(
    tmp_path, monkeypatch, mutation
):
    session_id = uuid4()
    identity = generation(session_id)
    path = runtime_state(tmp_path, session_id, identity)

    supplied = fence(identity)

    if mutation == "missing":
        supplied = None
    elif mutation == "malformed":
        supplied.pop("reservation_id")
    elif mutation == "reservation":
        supplied["reservation_id"] = str(uuid4())
    elif mutation == "node":
        supplied["node_id"] = str(uuid4())
    elif mutation == "gpu":
        supplied["gpu_uuid"] = "GPU-other"
    elif mutation == "runtime":
        supplied["runtime_id"] = f"kc-gaming-{uuid4()}"

    def forbidden(*args, **kwargs):
        raise AssertionError("Destructive cleanup must not execute")

    monkeypatch.setattr(
        gaming_runtime,
        "terminate_runtime_ownership",
        forbidden,
    )

    payload = {"session_id": str(session_id)}
    if supplied is not None:
        payload["delete_ownership_fence"] = supplied

    result = gaming_runtime.change_session_state(
        payload,
        state_root=tmp_path,
        execution_backend="windows_native",
        streaming_backend="sunshine",
        action="delete",
    )

    assert result.status == "blocked"
    assert path.exists()
    assert json.loads(path.read_text())["runtime_generation"] == identity


def test_delete_rejects_unfenced_existing_runtime(tmp_path):
    session_id = uuid4()
    identity = generation(session_id)
    path = runtime_state(tmp_path, session_id, identity)

    state = json.loads(path.read_text())
    del state["runtime_generation"]
    path.write_text(json.dumps(state))

    result = gaming_runtime.change_session_state(
        {
            "session_id": str(session_id),
            "delete_ownership_fence": fence(identity),
        },
        state_root=tmp_path,
        execution_backend="windows_native",
        streaming_backend="sunshine",
        action="delete",
    )

    assert result.status == "blocked"
    assert path.exists()


def test_fenced_delete_writes_receipt_and_matching_retry_succeeds(tmp_path):
    session_id = uuid4()
    identity = generation(session_id)
    state_path = runtime_state(tmp_path, session_id, identity)
    supplied = fence(identity)
    payload = {
        "session_id": str(session_id),
        "delete_ownership_fence": supplied,
    }

    first = gaming_runtime.change_session_state(
        payload,
        state_root=tmp_path,
        execution_backend="windows_native",
        streaming_backend="sunshine",
        action="delete",
    )

    assert first.status == "succeeded", first.error_message
    assert not state_path.exists()

    receipt_path = (
        tmp_path / "sessions" /
        f"kc-gaming-{session_id}.deleted.json"
    )
    assert receipt_path.exists()
    receipt = json.loads(receipt_path.read_text())
    assert receipt["delete_ownership_fence"] == supplied
    assert receipt["sanitized"] is True

    retry = gaming_runtime.change_session_state(
        payload,
        state_root=tmp_path,
        execution_backend="windows_native",
        streaming_backend="sunshine",
        action="delete",
    )
    assert retry.status == "succeeded"
    assert retry.result["idempotent"] is True


def test_delete_receipt_rejects_different_generation(tmp_path):
    session_id = uuid4()
    identity = generation(session_id)
    runtime_state(tmp_path, session_id, identity)
    supplied = fence(identity)

    first = gaming_runtime.change_session_state(
        {
            "session_id": str(session_id),
            "delete_ownership_fence": supplied,
        },
        state_root=tmp_path,
        execution_backend="windows_native",
        streaming_backend="sunshine",
        action="delete",
    )
    assert first.status == "succeeded"

    changed = dict(supplied)
    changed["billing_generation"] = str(uuid4())

    retry = gaming_runtime.change_session_state(
        {
            "session_id": str(session_id),
            "delete_ownership_fence": changed,
        },
        state_root=tmp_path,
        execution_backend="windows_native",
        streaming_backend="sunshine",
        action="delete",
    )
    assert retry.status == "blocked"


def test_delete_without_state_or_receipt_fails_closed(tmp_path):
    session_id = uuid4()
    supplied = fence(generation(session_id))

    result = gaming_runtime.change_session_state(
        {
            "session_id": str(session_id),
            "delete_ownership_fence": supplied,
        },
        state_root=tmp_path,
        execution_backend="windows_native",
        streaming_backend="sunshine",
        action="delete",
    )

    assert result.status == "blocked"
    assert "both absent" in result.error_message


def test_delete_receipt_does_not_allow_create_replay(tmp_path, monkeypatch):
    session_id = uuid4()
    identity = generation(session_id)
    runtime_state(tmp_path, session_id, identity)
    supplied = fence(identity)

    deleted = gaming_runtime.change_session_state(
        {
            "session_id": str(session_id),
            "delete_ownership_fence": supplied,
        },
        state_root=tmp_path,
        execution_backend="windows_native",
        streaming_backend="sunshine",
        action="delete",
    )
    assert deleted.status == "succeeded"

    created = gaming_runtime.create_session(
        {
            "session_id": str(session_id),
            "gpu_uuid": identity["gpu_uuid"],
            "runtime_generation": identity,
        },
        state_root=tmp_path,
        execution_backend="windows_native",
        streaming_backend="sunshine",
    )
    assert created.status == "blocked"
    assert "deletion receipt" in created.error_message


def test_delete_crash_after_receipt_before_state_removal_blocks_retry(
    tmp_path, monkeypatch
):
    session_id = uuid4()
    identity = generation(session_id)
    state_path = runtime_state(tmp_path, session_id, identity)
    supplied = fence(identity)

    original_unlink = type(state_path).unlink

    def interrupted_unlink(self, *args, **kwargs):
        if self == state_path:
            raise OSError("simulated crash before active-state removal")
        return original_unlink(self, *args, **kwargs)

    monkeypatch.setattr(type(state_path), "unlink", interrupted_unlink)

    payload = {
        "session_id": str(session_id),
        "delete_ownership_fence": supplied,
    }

    try:
        gaming_runtime.change_session_state(
            payload,
            state_root=tmp_path,
            execution_backend="windows_native",
            streaming_backend="sunshine",
            action="delete",
        )
    except OSError:
        pass

    assert state_path.exists()
    receipt_path = (
        tmp_path / "sessions" /
        f"kc-gaming-{session_id}.deleted.json"
    )
    assert receipt_path.exists()

    # Restore normal filesystem behavior before recovery.
    monkeypatch.setattr(type(state_path), "unlink", original_unlink)

    retry = gaming_runtime.change_session_state(
        payload,
        state_root=tmp_path,
        execution_backend="windows_native",
        streaming_backend="sunshine",
        action="delete",
    )

    assert retry.status == "succeeded", retry.error_message
    assert not state_path.exists()

    completed = json.loads(receipt_path.read_text())
    assert completed["runtime_state_deleted"] is True
    assert completed["delete_ownership_fence"] == supplied


def test_delete_receipt_with_active_state_rejects_other_generation(
    tmp_path
):
    session_id = uuid4()
    identity = generation(session_id)
    state_path = runtime_state(tmp_path, session_id, identity)

    receipt_path = (
        tmp_path / "sessions" /
        f"kc-gaming-{session_id}.deleted.json"
    )
    old_fence = fence(identity)

    receipt_path.write_text(json.dumps({
        "schema_version": 1,
        "runtime_id": identity["runtime_id"],
        "delete_ownership_fence": old_fence,
        "sanitized": True,
        "runtime_state_deleted": False,
    }))

    new_fence = dict(old_fence)
    new_fence["reservation_id"] = str(uuid4())

    result = gaming_runtime.change_session_state(
        {
            "session_id": str(session_id),
            "delete_ownership_fence": new_fence,
        },
        state_root=tmp_path,
        execution_backend="windows_native",
        streaming_backend="sunshine",
        action="delete",
    )

    assert result.status == "blocked"
    assert state_path.exists()
    assert receipt_path.exists()


def test_completed_receipt_records_state_removal(tmp_path):
    session_id = uuid4()
    identity = generation(session_id)
    state_path = runtime_state(tmp_path, session_id, identity)
    supplied = fence(identity)

    result = gaming_runtime.change_session_state(
        {
            "session_id": str(session_id),
            "delete_ownership_fence": supplied,
        },
        state_root=tmp_path,
        execution_backend="windows_native",
        streaming_backend="sunshine",
        action="delete",
    )

    assert result.status == "succeeded", result.error_message
    assert not state_path.exists()

    receipt_path = (
        tmp_path / "sessions" /
        f"kc-gaming-{session_id}.deleted.json"
    )
    receipt = json.loads(receipt_path.read_text())
    assert receipt["runtime_state_deleted"] is True
    assert receipt["sanitized"] is True


def test_malformed_receipt_fails_closed(tmp_path):
    session_id = uuid4()
    supplied = fence(generation(session_id))

    receipt_path = (
        tmp_path / "sessions" /
        f"kc-gaming-{session_id}.deleted.json"
    )
    receipt_path.parent.mkdir(parents=True, exist_ok=True)

    receipt_path.write_text(
        json.dumps({
            "schema_version": 1,
            "runtime_id": "incorrect-runtime",
            "delete_ownership_fence": supplied,
            "sanitized": True,
            "runtime_state_deleted": True,
        })
    )

    result = gaming_runtime.change_session_state(
        {
            "session_id": str(session_id),
            "delete_ownership_fence": supplied,
        },
        state_root=tmp_path,
        execution_backend="windows_native",
        streaming_backend="sunshine",
        action="delete",
    )

    assert result.status == "blocked"


def test_completed_receipt_conflicting_with_active_state_blocks(tmp_path):
    session_id = uuid4()
    identity = generation(session_id)
    state_path = runtime_state(tmp_path, session_id, identity)
    supplied = fence(identity)

    receipt_path = (
        tmp_path / "sessions" /
        f"kc-gaming-{session_id}.deleted.json"
    )
    receipt_path.write_text(
        json.dumps({
            "schema_version": 1,
            "runtime_id": f"kc-gaming-{session_id}",
            "delete_ownership_fence": supplied,
            "sanitized": True,
            "runtime_state_deleted": True,
        })
    )

    result = gaming_runtime.change_session_state(
        {
            "session_id": str(session_id),
            "delete_ownership_fence": supplied,
        },
        state_root=tmp_path,
        execution_backend="windows_native",
        streaming_backend="sunshine",
        action="delete",
    )

    assert result.status == "blocked"
    assert state_path.exists()


def test_delete_completion_write_crash_recovers_on_retry(
    tmp_path, monkeypatch
):
    session_id = uuid4()
    identity = generation(session_id)
    state_path = runtime_state(tmp_path, session_id, identity)
    supplied = fence(identity)
    payload = {
        "session_id": str(session_id),
        "delete_ownership_fence": supplied,
    }
    receipt_path = (
        tmp_path / "sessions" /
        f"kc-gaming-{session_id}.deleted.json"
    )

    original_write = gaming_runtime._write_state
    interrupted = {"count": 0}

    def crash_on_completion(path, value):
        if (
            path == receipt_path
            and value.get("runtime_state_deleted") is True
        ):
            interrupted["count"] += 1
            raise OSError("simulated interrupted receipt completion")
        return original_write(path, value)

    monkeypatch.setattr(
        gaming_runtime, "_write_state", crash_on_completion
    )

    try:
        result = gaming_runtime.change_session_state(
            payload,
            state_root=tmp_path,
            execution_backend="windows_native",
            streaming_backend="sunshine",
            action="delete",
        )
    except OSError:
        pass
    else:
        assert result.status != "succeeded"

    assert interrupted["count"] == 1
    assert not state_path.exists()
    assert receipt_path.exists()

    prepared = json.loads(receipt_path.read_text())
    assert prepared["runtime_state_deleted"] is False
    assert prepared["delete_ownership_fence"] == supplied

    monkeypatch.setattr(
        gaming_runtime, "_write_state", original_write
    )

    def forbidden_cleanup(*args, **kwargs):
        raise AssertionError("Retry must not repeat destructive cleanup")

    monkeypatch.setattr(
        gaming_runtime,
        "terminate_runtime_ownership",
        forbidden_cleanup,
    )

    retry = gaming_runtime.change_session_state(
        payload,
        state_root=tmp_path,
        execution_backend="windows_native",
        streaming_backend="sunshine",
        action="delete",
    )

    assert retry.status == "succeeded", retry.error_message
    assert retry.result["idempotent"] is True

    completed = json.loads(receipt_path.read_text())
    assert completed["runtime_state_deleted"] is True
    assert completed["delete_ownership_fence"] == supplied


def test_prepared_receipt_without_state_is_completed(
    tmp_path, monkeypatch
):
    session_id = uuid4()
    identity = generation(session_id)
    supplied = fence(identity)

    sessions = tmp_path / "sessions"
    sessions.mkdir(parents=True, exist_ok=True)

    receipt_path = (
        sessions / f"kc-gaming-{session_id}.deleted.json"
    )
    receipt_path.write_text(
        json.dumps({
            "schema_version": 1,
            "runtime_id": identity["runtime_id"],
            "delete_ownership_fence": supplied,
            "sanitized": True,
            "runtime_state_deleted": False,
        }),
        encoding="utf-8",
    )

    def forbidden_cleanup(*args, **kwargs):
        raise AssertionError("No active runtime may be cleaned")

    monkeypatch.setattr(
        gaming_runtime,
        "terminate_runtime_ownership",
        forbidden_cleanup,
    )

    result = gaming_runtime.change_session_state(
        {
            "session_id": str(session_id),
            "delete_ownership_fence": supplied,
        },
        state_root=tmp_path,
        execution_backend="windows_native",
        streaming_backend="sunshine",
        action="delete",
    )

    assert result.status == "succeeded", result.error_message
    assert result.result["idempotent"] is True
    assert (
        json.loads(receipt_path.read_text())["runtime_state_deleted"]
        is True
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", True),
        ("schema_version", 1.0),
        ("runtime_state_deleted", 0),
        ("runtime_state_deleted", 1),
        ("runtime_state_deleted", "false"),
        ("runtime_state_deleted", None),
    ],
)
def test_delete_rejects_receipt_wrong_json_types(
    tmp_path, field, value
):
    session_id = uuid4()
    identity = generation(session_id)
    supplied = fence(identity)

    receipt_path = (
        tmp_path / "sessions" /
        f"kc-gaming-{session_id}.deleted.json"
    )
    receipt_path.parent.mkdir(parents=True, exist_ok=True)

    receipt = {
        "schema_version": 1,
        "runtime_id": identity["runtime_id"],
        "delete_ownership_fence": supplied,
        "sanitized": True,
        "runtime_state_deleted": True,
    }
    receipt[field] = value
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    original_receipt = receipt_path.read_bytes()

    result = gaming_runtime.change_session_state(
        {
            "session_id": str(session_id),
            "delete_ownership_fence": supplied,
        },
        state_root=tmp_path,
        action="delete",
        execution_backend="windows_native",
        streaming_backend="sunshine",
    )

    assert result.status == "blocked"
    assert receipt_path.read_bytes() == original_receipt
    assert not (
        tmp_path / "sessions" /
        f"kc-gaming-{session_id}.json"
    ).exists()


def test_raw_e2e47_legacy_authorization_hardening(tmp_path):
    """Legacy evidence must not accept malformed operator authorization."""
    from khan_agent.gaming_runtime import (
        GamingRuntimeError,
        _legacy_retirement_evidence,
    )

    import pytest

    state_file = tmp_path / "legacy.json"
    state_file.write_text(
        '{"schema_version":1}',
        encoding="utf-8",
    )

    runtime_id = "kc-gaming-test"

    valid = {
        "legacy_retirement": True,
        "legacy_retirement_expected_state_sha256": "A" * 64,
        "legacy_runtime_id": runtime_id,
        "legacy_runtime_started_at": "2026-10-15T10:00:00+00:00",
        "requested_by_user_id": "operator-1",
        "legacy_retirement_reason": "Authorized legacy retirement",
    }

    for invalid_flag in ("true", 1, 0, None, False):
        payload = dict(valid)
        payload["legacy_retirement"] = invalid_flag

        with pytest.raises(
            GamingRuntimeError,
            match="explicit Boolean authorization",
        ):
            _legacy_retirement_evidence(
                payload=payload,
                state={"schema_version": 1},
                state_file=state_file,
                runtime_id=runtime_id,
            )

    for field in (
        "legacy_retirement_expected_state_sha256",
        "legacy_runtime_id",
        "legacy_runtime_started_at",
        "requested_by_user_id",
        "legacy_retirement_reason",
    ):
        payload = dict(valid)
        payload[field] = ""

        with pytest.raises(
            GamingRuntimeError,
            match="authorization evidence is incomplete",
        ):
            _legacy_retirement_evidence(
                payload=payload,
                state={"schema_version": 1},
                state_file=state_file,
                runtime_id=runtime_id,
            )

    with pytest.raises(
        GamingRuntimeError,
        match="generation-bound runtime state",
    ):
        _legacy_retirement_evidence(
            payload=valid,
            state={
                "schema_version": 1,
                "runtime_generation": {
                    "reservation_id": "reservation-1",
                },
            },
            state_file=state_file,
            runtime_id=runtime_id,
        )
