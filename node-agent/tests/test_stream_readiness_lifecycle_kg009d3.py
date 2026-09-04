from __future__ import annotations

import inspect

from khan_agent import gaming
from khan_agent import gaming_runtime


def _function_source(function):
    return inspect.getsource(function)


def test_create_dispatch_threads_sunshine_configuration():
    text = _function_source(gaming.execute_gaming_job)

    create = text[
        text.index('if job_type == "gaming.session.create":'):
        text.index(
            'action = job_type.rsplit(".", 1)[-1]'
        )
    ]

    assert "sunshine_api_url=sunshine_api_url" in create
    assert (
        "sunshine_api_username=sunshine_api_username"
        in create
    )
    assert (
        "sunshine_api_password=sunshine_api_password"
        in create
    )
    assert "sunshine_verify_tls=sunshine_verify_tls" in create


def test_create_requires_readiness_before_running_state():
    text = _function_source(gaming_runtime.create_session)

    verify = text.index("readiness = _verify_stream_readiness(")
    running = text.index(
        '"status": "running"',
        verify,
    )
    ready = text.index(
        '"runtime_stage": "stream_ready"',
        running,
    )

    assert verify < running < ready
    assert '"stream_readiness": readiness' in text


def test_idempotent_running_create_revalidates_readiness():
    text = _function_source(gaming_runtime.create_session)

    block_start = text.index(
        'if existing.get("status") == "running":'
    )
    block_end = text.index(
        'if existing.get("display_policy") is not None:',
        block_start,
    )
    block = text[block_start:block_end]

    assert "_verify_stream_readiness(" in block
    assert 'existing["stream_readiness"] = readiness' in block
    assert 'existing["runtime_stage"] = "stream_ready"' in block


def test_start_paths_require_readiness():
    text = _function_source(
        gaming_runtime.change_session_state
    )

    assert text.count("_verify_stream_readiness(") >= 2
    assert text.count(
        'state["stream_readiness"] = readiness'
    ) >= 2


def test_reconciliation_never_promotes_starting_to_stream_ready():
    text = _function_source(
        gaming_runtime.reconcile_runtime_ownership
    )

    assert '"recovered_running"' not in text
    assert '"readiness_pending"' in text
    assert (
        'state["status"] = "running"'
        not in text
    )
    assert (
        '] = "stream_ready"'
        not in text
    )


def test_stream_readiness_normalizes_sunshine_failure():
    text = _function_source(
        gaming_runtime._verify_stream_readiness
    )

    assert "except SunshineBrokerError as exc:" in text
    assert (
        "Sunshine stream readiness could not be verified"
        in text
    )
