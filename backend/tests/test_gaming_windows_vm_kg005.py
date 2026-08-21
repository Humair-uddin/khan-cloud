from pathlib import Path
from pydantic import ValidationError
import pytest
from app.schemas.compute import GamingSessionCreate, GamingVmBlueprintCreate

def test_session_supports_explicit_windows_vm_mode():
    p=GamingSessionCreate(name="cs2-vm",deployment_mode="proxmox_windows_vm",blueprint_slug="windows-gaming-v1")
    assert p.deployment_mode=="proxmox_windows_vm"

def test_vm_blueprint_contract_is_fail_closed():
    with pytest.raises(ValidationError): GamingVmBlueprintCreate(slug="bad",name="bad",template_vmid=1)
    p=GamingVmBlueprintCreate(slug="windows-gaming-v1",name="Windows Gaming V1",template_vmid=9000)
    assert p.bootstrap_mode=="prebaked_agent_qga" and p.reset_policy=="destroy_on_terminate"

def test_scheduler_has_separate_hypervisor_path():
    root=Path(__file__).resolve().parents[1]; src=(root/"app/services/gaming_vm_service.py").read_text()
    assert "select_gaming_hypervisor" in src and "gpu_passthrough" in src and "virtualization_ready" in src

def test_guest_enrollment_is_one_time_and_correlated():
    root=Path(__file__).resolve().parents[1]; src=(root/"app/services/gaming_vm_service.py").read_text()
    assert "create_guest_enrollment_profile" in src and 'max_uses=1' in src and '"gaming_session_id"' in src

def test_connection_lease_targets_guest_node_when_present():
    root=Path(__file__).resolve().parents[1]; src=(root/"app/services/gaming_connection_service.py").read_text()
    assert "session.guest_node_id or session.node_id" in src

def test_vm_job_secret_is_redacted_after_completion():
    root=Path(__file__).resolve().parents[1]; src=(root/"app/services/gaming_vm_service.py").read_text()
    assert "scrub_vm_job_secret" in src and '"[REDACTED]"' in src


def test_kg005b_blueprint_metadata_reaches_hypervisor_job():
    root=Path(__file__).resolve().parents[1]
    src=(root/"app/services/gaming_vm_service.py").read_text()
    assert '"blueprint_metadata":dict(blueprint.metadata_json or {})' in src

def test_kg005b_guest_registration_updates_connection_identity():
    root=Path(__file__).resolve().parents[1]
    src=(root/"app/services/gaming_vm_service.py").read_text()
    assert '"guest_node_id":str(node.id)' in src
    assert '"guest_ip":node.production_ip or node.management_ip' in src
