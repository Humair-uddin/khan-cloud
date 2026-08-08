from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.provider_onboarding_service import (
    ProviderOnboardingError,
    _profile_settings_for_role,
    hash_download_token,
)


def user(*roles, superuser=False):
    return SimpleNamespace(is_superuser=superuser, roles=[SimpleNamespace(name=r, permissions=[]) for r in roles])


def test_download_token_is_hashed_not_stored_plaintext():
    token = "kcinst_example-secret"
    digest = hash_download_token(token)
    assert token not in digest
    assert len(digest) == 64


def test_operator_can_generate_vps_host_profile():
    settings = _profile_settings_for_role(user("operator"), "vps_host")
    assert settings["purpose"] == "vps_infrastructure"
    assert settings["resource_policy"]["auto_approve_node"] is True


def test_customer_cannot_generate_khan_cloud_vps_infrastructure():
    with pytest.raises(ProviderOnboardingError):
        _profile_settings_for_role(user("customer"), "vps_host")


def test_customer_can_generate_private_compute_installer():
    settings = _profile_settings_for_role(user("customer"), "private_compute")
    assert settings["purpose"] == "organization_private"
    assert settings["ownership_type"] == "organization"
    assert settings["resource_policy"]["auto_approve_node"] is True


def test_provider_api_and_frontend_are_wired():
    root = Path(__file__).resolve().parents[1]
    api = (root / "app" / "api" / "v1" / "provider.py").read_text()
    main = (root / "app" / "main.py").read_text()
    assert '"/node-installers"' in api
    assert '"/bootstrap/{token}"' in api
    assert "provider_router" in main


def test_installer_generation_uses_universal_run_builder():
    root = Path(__file__).resolve().parents[1]
    source = (root / "app" / "services" / "provider_onboarding_service.py").read_text()
    assert "build-universal-run.py" in source
    assert "universal-bootstrap.sh" in source
    assert "deployment_enrollment_code" in source
    assert "verify_tls" in source


def test_live_validation_script_uses_public_bootstrap_download():
    root = Path(__file__).resolve().parents[1]
    source = (root / "scripts" / "validate-provider-onboarding.py").read_text()
    assert "/api/v1/provider/bootstrap/{token}" in source
    assert "response.content.startswith" in source
    assert "validation_cleanup" in source
