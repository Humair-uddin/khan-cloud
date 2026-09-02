from pathlib import Path

from khan_agent import windows_interactive
from khan_agent import windows_job_supervisor


def test_windows_launch_is_suspended_before_job_assignment():
    source = Path(
        windows_interactive.__file__
    ).read_text()

    created = source.index(
        "CREATE_SUSPENDED"
    )
    assigned = source.index(
        "AssignProcessToJobObject"
    )
    resumed = source.index(
        "ResumeThread"
    )

    assert created < assigned < resumed


def test_windows_job_supervisor_uses_kill_on_close():
    source = Path(
        windows_job_supervisor.__file__
    ).read_text()

    assert (
        "JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE"
        in source
    )
    assert "CreateJobObjectW" in source
    assert "SetInformationJobObject" in source


def test_windows_job_supervisor_survives_agent_handle_close_contract():
    source = Path(
        windows_interactive.__file__
    ).read_text()

    supervisor = source.index(
        "windows_job_supervisor"
    )
    assignment = source.index(
        "AssignProcessToJobObject"
    )

    assert supervisor < assignment


def test_windows_job_ownership_contains_no_process_name_sweep():
    source = (
        Path(
            windows_interactive.__file__
        ).read_text()
        + Path(
            windows_job_supervisor.__file__
        ).read_text()
    ).lower()

    assert "taskkill" not in source
    assert "get-process" not in source
