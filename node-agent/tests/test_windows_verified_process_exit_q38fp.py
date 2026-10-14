from pathlib import Path

import khan_agent.windows_verified_process as w


SOURCE = (
    Path(__file__).resolve().parents[1]
    / "khan_agent"
    / "windows_verified_process.py"
)


def test_q38fp_wait_timeout_constant_is_declared():
    assert w.WAIT_OBJECT_0 == 0
    assert w.WAIT_TIMEOUT == 0x102


def test_q38fp_read_identity_checks_exit_before_identity_query():
    source = SOURCE.read_text(encoding="utf-8")

    start = source.index("def read_process_identity(")
    end = source.index(
        "\ndef ",
        start + len("def read_process_identity("),
    )
    function = source[start:end]

    wait = function.index("WaitForSingleObject(")
    retired = function.index("if wait == WAIT_OBJECT_0:")
    identity = function.index("_read_identity_from_handle(")

    assert wait < retired < identity
    assert "return None, None" in function
    assert "if wait != WAIT_TIMEOUT:" in function


def test_q38fp_does_not_special_case_query_image_error_31():
    source = SOURCE.read_text(encoding="utf-8")

    start = source.index("def read_process_identity(")
    end = source.index(
        "\ndef ",
        start + len("def read_process_identity("),
    )
    function = source[start:end]

    assert "error == 31" not in function
    assert "error in {31" not in function


def test_q38fp_termination_still_waits_for_exact_process_handle():
    source = SOURCE.read_text(encoding="utf-8")

    start = source.index(
        "def terminate_verified_process_ownership("
    )
    function = source[start:]

    assert "TerminateProcess(" in function
    assert "WaitForSingleObject(" in function
    assert "WAIT_OBJECT_0" in function
