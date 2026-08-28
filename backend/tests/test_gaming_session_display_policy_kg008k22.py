from pathlib import Path

import pytest
from pydantic import ValidationError

from app.schemas.compute import GamingSessionCreate
from app.services.gaming_display_policy import (
    GamingDisplayPolicyError,
    constraints_for_session_request,
    derive_display_policy,
)
from app.services.gaming_service import (
    _gaming_session_display_policy,
)


def test_old_gaming_session_request_remains_valid():
    payload = GamingSessionCreate(
        name="legacy-session",
    )

    assert payload.display_profile == "auto"
    assert payload.display_max_width is None
    assert payload.display_max_height is None
    assert payload.display_max_refresh_hz is None
    assert payload.hdr_requested is False


def test_auto_profile_is_safe_4k120_not_240():
    payload = GamingSessionCreate(
        name="auto-session",
    )

    policy = _gaming_session_display_policy(
        payload
    )

    assert policy["preferred_mode"] == {
        "width": 3840,
        "height": 2160,
        "refresh_hz": 120,
    }

    assert all(
        mode["refresh_hz"] < 240
        for mode in policy["modes"]
    )


def test_standard_profile_maps_to_1080p60():
    payload = GamingSessionCreate(
        name="standard-session",
        display_profile="standard",
    )

    policy = _gaming_session_display_policy(
        payload
    )

    assert policy["preferred_mode"] == {
        "width": 1920,
        "height": 1080,
        "refresh_hz": 60,
    }


def test_performance_profile_maps_to_1440p120():
    payload = GamingSessionCreate(
        name="performance-session",
        display_profile="performance",
    )

    policy = _gaming_session_display_policy(
        payload
    )

    assert policy["preferred_mode"] == {
        "width": 2560,
        "height": 1440,
        "refresh_hz": 120,
    }


def test_competitive_profile_maps_to_1440p165():
    payload = GamingSessionCreate(
        name="competitive-session",
        display_profile="competitive",
    )

    policy = _gaming_session_display_policy(
        payload
    )

    assert policy["preferred_mode"] == {
        "width": 2560,
        "height": 1440,
        "refresh_hz": 165,
    }


def test_ultra_competitive_maps_to_1440p240():
    payload = GamingSessionCreate(
        name="ultra-session",
        display_profile="ultra_competitive",
    )

    policy = _gaming_session_display_policy(
        payload
    )

    assert policy["preferred_mode"] == {
        "width": 2560,
        "height": 1440,
        "refresh_hz": 240,
    }


def test_quality_profile_maps_to_4k120():
    payload = GamingSessionCreate(
        name="quality-session",
        display_profile="quality",
    )

    policy = _gaming_session_display_policy(
        payload
    )

    assert policy["preferred_mode"] == {
        "width": 3840,
        "height": 2160,
        "refresh_hz": 120,
    }


def test_client_cap_can_reduce_product_profile():
    payload = GamingSessionCreate(
        name="client-capped",
        display_profile="quality",
        display_max_width=1920,
        display_max_height=1080,
        display_max_refresh_hz=60,
    )

    policy = _gaming_session_display_policy(
        payload
    )

    assert policy["preferred_mode"] == {
        "width": 1920,
        "height": 1080,
        "refresh_hz": 60,
    }


def test_client_cap_cannot_expand_standard_to_4k():
    payload = GamingSessionCreate(
        name="no-upgrade",
        display_profile="standard",
        display_max_width=3840,
        display_max_height=2160,
        display_max_refresh_hz=240,
        display_allow_4k=True,
        display_allow_240hz=True,
    )

    policy = _gaming_session_display_policy(
        payload
    )

    assert policy["preferred_mode"] == {
        "width": 1920,
        "height": 1080,
        "refresh_hz": 60,
    }


def test_explicit_preferred_mode_supported_inside_tier():
    payload = GamingSessionCreate(
        name="explicit",
        display_profile="competitive",
        display_preferred_width=1920,
        display_preferred_height=1080,
        display_preferred_refresh_hz=144,
    )

    policy = _gaming_session_display_policy(
        payload
    )

    assert policy["preferred_mode"] == {
        "width": 1920,
        "height": 1080,
        "refresh_hz": 144,
    }


def test_preferred_mode_outside_tier_fails_closed():
    payload = GamingSessionCreate(
        name="invalid-preference",
        display_profile="standard",
        display_preferred_width=2560,
        display_preferred_height=1440,
        display_preferred_refresh_hz=120,
    )

    with pytest.raises(
        GamingDisplayPolicyError
    ):
        _gaming_session_display_policy(
            payload
        )


def test_hdr_request_without_client_capability_is_sdr():
    payload = GamingSessionCreate(
        name="hdr-fallback",
        hdr_requested=True,
        client_hdr_capable=False,
    )

    policy = _gaming_session_display_policy(
        payload
    )

    assert policy["hdr_enabled"] is False
    assert policy["bit_depth"] == 8
    assert policy["color_space"] == "RGB"


def test_hdr_request_with_capability_generates_hdr_policy():
    payload = GamingSessionCreate(
        name="hdr-session",
        hdr_requested=True,
        client_hdr_capable=True,
    )

    policy = _gaming_session_display_policy(
        payload
    )

    assert policy["hdr_enabled"] is True
    assert policy["bit_depth"] == 10
    assert policy["color_space"] == "Rec.2020"


def test_unknown_display_profile_fails_closed():
    payload = GamingSessionCreate(
        name="unknown-tier",
        display_profile="warp-speed",
    )

    with pytest.raises(
        GamingDisplayPolicyError
    ):
        _gaming_session_display_policy(
            payload
        )


def test_policy_is_deterministic_for_same_session_intent():
    payload = GamingSessionCreate(
        name="stable",
        display_profile="competitive",
        display_max_refresh_hz=144,
    )

    first = _gaming_session_display_policy(
        payload
    )

    second = _gaming_session_display_policy(
        payload
    )

    assert (
        first["policy_version"]
        == second["policy_version"]
    )


def test_policy_contract_never_expands_beyond_historical_14():
    payload = GamingSessionCreate(
        name="maximum",
        display_profile="quality",
        display_max_width=7680,
        display_max_height=4320,
        display_max_refresh_hz=500,
        display_allow_4k=True,
        display_allow_240hz=True,
    )

    policy = _gaming_session_display_policy(
        payload
    )

    emitted = {
        (
            item["width"],
            item["height"],
            item["refresh_hz"],
        )
        for item in policy["modes"]
    }

    assert (3840, 2160, 144) not in emitted
    assert (3840, 2160, 240) not in emitted
    assert max(
        item[0]
        for item in emitted
    ) <= 3840


def test_gaming_service_source_injects_policy_into_existing_job():
    root = Path(__file__).resolve().parents[1]

    source = (
        root
        / "app"
        / "services"
        / "gaming_service.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "display_policy = "
        "_gaming_session_display_policy(payload)"
        in source
    )

    assert (
        '"display_policy":display_policy'
        in source
        or '"display_policy": display_policy'
        in source
    )

    assert 'job_type="gaming.session.create"' in source
