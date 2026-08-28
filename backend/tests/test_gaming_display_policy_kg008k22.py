from app.services.gaming_display_policy import (
    CONTRACT_VERSION,
    HISTORICAL_14_MODES,
    DisplayMode,
    DisplayPolicyConstraints,
    GamingDisplayPolicyError,
    allowed_modes,
    attach_display_policy,
    derive_display_policy,
)


EXPECTED_14 = (
    DisplayMode(1280, 720, 30),
    DisplayMode(1280, 720, 60),
    DisplayMode(1920, 1080, 60),
    DisplayMode(1920, 1080, 120),
    DisplayMode(1920, 1080, 144),
    DisplayMode(1920, 1080, 165),
    DisplayMode(1920, 1080, 240),
    DisplayMode(2560, 1440, 60),
    DisplayMode(2560, 1440, 120),
    DisplayMode(2560, 1440, 144),
    DisplayMode(2560, 1440, 165),
    DisplayMode(2560, 1440, 240),
    DisplayMode(3840, 2160, 60),
    DisplayMode(3840, 2160, 120),
)


def test_historical_14_capability_envelope_exact():
    assert HISTORICAL_14_MODES == EXPECTED_14
    assert len(HISTORICAL_14_MODES) == 14
    assert len(set(HISTORICAL_14_MODES)) == 14


def test_default_constraints_expose_exact_historical_14():
    assert allowed_modes(
        DisplayPolicyConstraints()
    ) == EXPECTED_14


def test_default_policy_prefers_4k120():
    policy = derive_display_policy(
        DisplayPolicyConstraints()
    )

    assert policy["preferred_mode"] == {
        "width": 3840,
        "height": 2160,
        "refresh_hz": 120,
    }


def test_1080p_60_cap():
    policy = derive_display_policy(
        DisplayPolicyConstraints(
            max_width=1920,
            max_height=1080,
            max_refresh_hz=60,
        )
    )

    assert policy["preferred_mode"] == {
        "width": 1920,
        "height": 1080,
        "refresh_hz": 60,
    }

    assert all(
        mode["width"] <= 1920
        and mode["height"] <= 1080
        and mode["refresh_hz"] <= 60
        for mode in policy["modes"]
    )


def test_1080p_165_competitive_cap():
    policy = derive_display_policy(
        DisplayPolicyConstraints(
            max_width=1920,
            max_height=1080,
            max_refresh_hz=165,
        )
    )

    assert policy["preferred_mode"] == {
        "width": 1920,
        "height": 1080,
        "refresh_hz": 165,
    }


def test_1080p_240_cap():
    policy = derive_display_policy(
        DisplayPolicyConstraints(
            max_width=1920,
            max_height=1080,
            max_refresh_hz=240,
        )
    )

    assert policy["preferred_mode"] == {
        "width": 1920,
        "height": 1080,
        "refresh_hz": 240,
    }


def test_1440p_120_cap():
    policy = derive_display_policy(
        DisplayPolicyConstraints(
            max_width=2560,
            max_height=1440,
            max_refresh_hz=120,
        )
    )

    assert policy["preferred_mode"] == {
        "width": 2560,
        "height": 1440,
        "refresh_hz": 120,
    }


def test_1440p_240_cap():
    policy = derive_display_policy(
        DisplayPolicyConstraints(
            max_width=2560,
            max_height=1440,
            max_refresh_hz=240,
        )
    )

    assert policy["preferred_mode"] == {
        "width": 2560,
        "height": 1440,
        "refresh_hz": 240,
    }


def test_4k_60_cap():
    policy = derive_display_policy(
        DisplayPolicyConstraints(
            max_width=3840,
            max_height=2160,
            max_refresh_hz=60,
        )
    )

    assert policy["preferred_mode"] == {
        "width": 3840,
        "height": 2160,
        "refresh_hz": 60,
    }


def test_disallow_4k_removes_4k():
    policy = derive_display_policy(
        DisplayPolicyConstraints(
            allow_4k=False,
        )
    )

    assert all(
        mode["width"] < 3840
        for mode in policy["modes"]
    )


def test_disallow_240_removes_240():
    policy = derive_display_policy(
        DisplayPolicyConstraints(
            allow_240hz=False,
        )
    )

    assert all(
        mode["refresh_hz"] < 240
        for mode in policy["modes"]
    )


def test_explicit_preferred_mode_must_be_allowed():
    policy = derive_display_policy(
        DisplayPolicyConstraints(
            max_width=2560,
            max_height=1440,
            max_refresh_hz=165,
            preferred_width=1920,
            preferred_height=1080,
            preferred_refresh_hz=144,
        )
    )

    assert policy["preferred_mode"] == {
        "width": 1920,
        "height": 1080,
        "refresh_hz": 144,
    }


def test_explicit_preferred_outside_allowed_fails():
    try:
        derive_display_policy(
            DisplayPolicyConstraints(
                max_width=1920,
                max_height=1080,
                max_refresh_hz=120,
                preferred_width=2560,
                preferred_height=1440,
                preferred_refresh_hz=120,
            )
        )
    except GamingDisplayPolicyError:
        pass
    else:
        raise AssertionError(
            "Expected invalid preferred mode rejection."
        )


def test_partial_preferred_mode_fails():
    try:
        derive_display_policy(
            DisplayPolicyConstraints(
                preferred_width=1920,
            )
        )
    except GamingDisplayPolicyError:
        pass
    else:
        raise AssertionError(
            "Expected partial preferred mode rejection."
        )


def test_empty_intersection_fails_closed():
    try:
        derive_display_policy(
            DisplayPolicyConstraints(
                min_width=5000,
                max_width=6000,
                min_height=3000,
                max_height=4000,
            )
        )
    except GamingDisplayPolicyError:
        pass
    else:
        raise AssertionError(
            "Expected no-mode failure."
        )


def test_hdr_requested_but_not_capable_falls_back_to_sdr():
    policy = derive_display_policy(
        DisplayPolicyConstraints(
            hdr_requested=True,
            hdr_capable=False,
        )
    )

    assert policy["hdr_enabled"] is False
    assert policy["bit_depth"] == 8
    assert policy["color_space"] == "RGB"


def test_hdr_capable_but_not_requested_remains_sdr():
    policy = derive_display_policy(
        DisplayPolicyConstraints(
            hdr_requested=False,
            hdr_capable=True,
        )
    )

    assert policy["hdr_enabled"] is False
    assert policy["bit_depth"] == 8
    assert policy["color_space"] == "RGB"


def test_hdr_requires_both_request_and_capability():
    policy = derive_display_policy(
        DisplayPolicyConstraints(
            hdr_requested=True,
            hdr_capable=True,
        )
    )

    assert policy["hdr_enabled"] is True
    assert policy["bit_depth"] == 10
    assert policy["color_space"] == "Rec.2020"


def test_policy_contract_version_present():
    policy = derive_display_policy(
        DisplayPolicyConstraints()
    )

    assert policy["contract_version"] == CONTRACT_VERSION


def test_policy_version_is_deterministic():
    constraints = DisplayPolicyConstraints(
        max_width=2560,
        max_height=1440,
        max_refresh_hz=165,
    )

    first = derive_display_policy(constraints)
    second = derive_display_policy(constraints)

    assert first["policy_version"] == second["policy_version"]


def test_policy_version_changes_when_effective_policy_changes():
    first = derive_display_policy(
        DisplayPolicyConstraints(
            max_width=1920,
            max_height=1080,
            max_refresh_hz=120,
        )
    )

    second = derive_display_policy(
        DisplayPolicyConstraints(
            max_width=1920,
            max_height=1080,
            max_refresh_hz=165,
        )
    )

    assert first["policy_version"] != second["policy_version"]


def test_attach_policy_does_not_mutate_input():
    source = {
        "session_id": "session-1",
        "gpu_uuid": "GPU-1",
    }

    result = attach_display_policy(
        source,
        DisplayPolicyConstraints(
            max_width=1920,
            max_height=1080,
            max_refresh_hz=165,
        ),
    )

    assert "display_policy" not in source
    assert "display_policy" in result
    assert result["session_id"] == "session-1"


def test_attach_refuses_existing_display_policy():
    source = {
        "session_id": "session-1",
        "display_policy": {
            "policy_version": "caller-owned",
        },
    }

    try:
        attach_display_policy(
            source,
            DisplayPolicyConstraints(),
        )
    except GamingDisplayPolicyError:
        pass
    else:
        raise AssertionError(
            "Expected duplicate policy injection rejection."
        )


def test_selector_never_emits_mode_outside_historical_envelope():
    policy = derive_display_policy(
        DisplayPolicyConstraints()
    )

    emitted = {
        DisplayMode(
            mode["width"],
            mode["height"],
            mode["refresh_hz"],
        )
        for mode in policy["modes"]
    }

    assert emitted <= set(HISTORICAL_14_MODES)


def test_no_4k_144_or_4k_240_can_be_emitted():
    policy = derive_display_policy(
        DisplayPolicyConstraints(
            max_width=7680,
            max_height=4320,
            max_refresh_hz=240,
        )
    )

    emitted = {
        (
            mode["width"],
            mode["height"],
            mode["refresh_hz"],
        )
        for mode in policy["modes"]
    }

    assert (3840, 2160, 144) not in emitted
    assert (3840, 2160, 165) not in emitted
    assert (3840, 2160, 240) not in emitted
