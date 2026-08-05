from datetime import UTC, datetime, timedelta

import pytest

from app.schemas.deployment_profile import DeploymentProfileCreate
from app.services.deployment_profile_service import (
    DeploymentProfileError,
    _validate_profile_policy,
    hash_enrollment_code,
)


def test_enrollment_code_hash_is_stable() -> None:
    assert hash_enrollment_code("abc") == hash_enrollment_code("abc")
    assert hash_enrollment_code("abc") != hash_enrollment_code("def")


def test_public_third_party_vps_is_rejected() -> None:
    payload = DeploymentProfileCreate(
        name="Bad VPS",
        purpose="vps_infrastructure",
        ownership_type="third_party_provider",
        visibility="public_marketplace",
        control_plane_url="https://cloud.example.com",
    )
    with pytest.raises(DeploymentProfileError):
        _validate_profile_policy(payload)


def test_internal_lab_requires_internal_visibility() -> None:
    payload = DeploymentProfileCreate(
        name="Lab",
        purpose="internal_lab",
        ownership_type="khan_cloud",
        visibility="organization_only",
        control_plane_url="http://192.168.18.100:8000",
    )
    with pytest.raises(DeploymentProfileError):
        _validate_profile_policy(payload)
