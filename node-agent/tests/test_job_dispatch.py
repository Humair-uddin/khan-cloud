from pathlib import Path

from khan_agent.job_dispatch import execute_node_job


COMMON = {
    "virtualization_execution_enabled": False,
    "virtualization_storage_root": Path("/tmp/khan-cloud-test-vps"),
    "virtualization_base_image_path": Path("/tmp/nonexistent-base.qcow2"),
    "virtualization_network_name": "kc-test",
}


def test_gaming_probe_routes_to_gaming_executor():
    result = execute_node_job(
        {
            "job_type": "gaming.probe",
            "payload": {},
        },
        **COMMON,
    )

    assert result.status == "succeeded"
    assert result.result["workload_family"] == "gaming"
    assert result.result["executor"] == "khan_agent.gaming"
    assert result.result["probe"] == "ok"
    assert result.error_message == ""


def test_unknown_workload_is_rejected():
    result = execute_node_job(
        {
            "job_type": "unknown.test",
            "payload": {},
        },
        **COMMON,
    )

    assert result.status == "failed"
    assert result.result == {}
    assert "Unsupported node job type" in result.error_message


def test_vps_jobs_still_route_to_existing_virtualization_executor():
    result = execute_node_job(
        {
            "job_type": "vps.create",
            "payload": {},
        },
        **COMMON,
    )

    assert result.status == "blocked"
    assert "VPS execution is disabled by node policy" in result.error_message
    assert "virtualization" in result.result


def test_gaming_executor_rejects_unknown_gaming_operation():
    result = execute_node_job(
        {
            "job_type": "gaming.not-real",
            "payload": {},
        },
        **COMMON,
    )

    assert result.status == "failed"
    assert "Unsupported gaming job type" in result.error_message
