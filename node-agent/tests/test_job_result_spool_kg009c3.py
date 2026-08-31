from pathlib import Path

from khan_agent.job_result_spool import JobResultSpool


def test_result_spool_round_trip(tmp_path):
    spool = JobResultSpool(tmp_path / "results")
    payload = {
        "status": "succeeded",
        "result": {"runtime_id": "gaming-session-1"},
        "error_message": "",
    }

    path = spool.save("job-1", payload)

    assert path.exists()
    entries = spool.pending()
    assert len(entries) == 1
    assert entries[0].job_id == "job-1"
    assert entries[0].payload == payload

    spool.remove("job-1")
    assert spool.pending() == []


def test_spool_uses_atomic_replace_contract():
    source = Path(JobResultSpool.__module__.replace(".", "/") + ".py")
    if not source.exists():
        source = Path(__file__).parents[1] / "khan_agent" / "job_result_spool.py"
    text = source.read_text()

    assert "os.fsync" in text
    assert "os.replace" in text


def test_agent_persists_result_before_reporting():
    runtime = (
        Path(__file__).parents[1]
        / "khan_agent"
        / "runtime.py"
    ).read_text()

    saved = runtime.index("self.job_result_spool.save")
    reported = runtime.index("await self.client.report_job_result", saved)
    removed = runtime.index("self.job_result_spool.remove", reported)

    assert saved < reported < removed


def test_agent_flushes_spool_before_claiming_new_job():
    runtime = (
        Path(__file__).parents[1]
        / "khan_agent"
        / "runtime.py"
    ).read_text()

    flush = runtime.index("await self._flush_job_result_spool(credentials)")
    claim = runtime.index("job = await next_job(credentials)", flush)

    assert flush < claim
