from pathlib import Path

from khan_agent import windows_interactive


def _source() -> str:
    return Path(
        windows_interactive.__file__
    ).read_text()


def test_job_supervisor_has_deterministic_runtime_cwd():
    source = _source()

    assert (
        "Path(__file__).resolve().parents[1]"
        in source
    )

    supervisor = source.index(
        '"khan_agent.windows_job_supervisor"'
    )

    cwd = source.index(
        "cwd=runtime_root",
        supervisor,
    )

    assert supervisor < cwd


def test_failed_ownership_setup_terminates_created_child():
    source = _source()

    failure_cleanup = source.index(
        "process_handle.TerminateProcess(1)"
    )

    wait = source.index(
        "win32event.WaitForSingleObject(",
        failure_cleanup,
    )

    close = source.index(
        "process_handle.Close()",
        failure_cleanup,
    )

    assert failure_cleanup < wait < close


def test_child_is_suspended_until_job_assignment():
    source = _source()

    suspended = source.index(
        "win32con.CREATE_SUSPENDED"
    )

    assignment = source.index(
        "kernel32.AssignProcessToJobObject"
    )

    resume = source.index(
        "win32process.ResumeThread(thread_handle)"
    )

    assert suspended < assignment < resume


def test_windows_launcher_resolves_bare_executable_before_createprocess():
    source = Path(
        "khan_agent/windows_interactive.py"
    ).read_text(encoding="utf-8")

    assert "requested_executable = argv[0]" in source
    assert "shutil.which(requested_executable)" in source
    assert "resolved_argv = [" in source
    assert "command_line = subprocess.list2cmdline(resolved_argv)" in source

    create_index = source.index(
        "win32process.CreateProcessAsUser("
    )
    resolve_index = source.index(
        "shutil.which(requested_executable)"
    )

    assert resolve_index < create_index


def test_windows_launcher_preserves_explicit_executable_paths():
    source = Path(
        "khan_agent/windows_interactive.py"
    ).read_text(encoding="utf-8")

    assert "if os.path.dirname(requested_executable):" in source
    assert "executable = requested_executable" in source
    assert "Unable to resolve interactive executable:" in source
