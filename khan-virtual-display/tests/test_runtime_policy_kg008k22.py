from __future__ import annotations

import importlib.util
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "control" / "runtime_policy.py"
TEMPLATE = ROOT / "config" / "khan-vdd-settings.xml"

spec = importlib.util.spec_from_file_location(
    "khan_vdd_runtime_policy",
    MODULE,
)
assert spec is not None
assert spec.loader is not None

runtime_policy = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = runtime_policy
spec.loader.exec_module(runtime_policy)

DisplayMode = runtime_policy.DisplayMode
RuntimeDisplayPolicy = runtime_policy.RuntimeDisplayPolicy


EXPECTED_14 = (
    DisplayMode(3840, 2160, 60),
    DisplayMode(2560, 1440, 120),
    DisplayMode(2560, 1440, 60),
    DisplayMode(1920, 1080, 120),
    DisplayMode(1920, 1080, 60),
    DisplayMode(1280, 720, 60),
    DisplayMode(1280, 720, 30),
    DisplayMode(3840, 2160, 120),
    DisplayMode(2560, 1440, 240),
    DisplayMode(2560, 1440, 165),
    DisplayMode(2560, 1440, 144),
    DisplayMode(1920, 1080, 240),
    DisplayMode(1920, 1080, 165),
    DisplayMode(1920, 1080, 144),
)


def policy(**kwargs):
    values = {
        "policy_version": "kg008-k22-test-v1",
        "modes": EXPECTED_14,
        "preferred_mode": DisplayMode(
            1920, 1080, 60
        ),
        "hdr_enabled": False,
        "bit_depth": 10,
        "color_space": "RGB",
    }
    values.update(kwargs)
    return RuntimeDisplayPolicy(**values)


def modes_from(path):
    root = ET.parse(path).getroot()
    return tuple(
        DisplayMode(
            int(node.findtext("width")),
            int(node.findtext("height")),
            int(node.findtext("refresh_rate")),
        )
        for node in root.findall(
            "./resolutions/resolution"
        )
    )


def test_contract_version():
    assert (
        runtime_policy.CONTRACT_VERSION
        == "kg008k-runtime-policy-v1"
    )


def test_historical_14_policy_is_accepted():
    policy().validate()


def test_duplicate_modes_fail_closed():
    with pytest.raises(ValueError):
        policy(
            modes=EXPECTED_14 + (EXPECTED_14[0],)
        ).validate()


def test_out_of_range_refresh_fails_closed():
    with pytest.raises(ValueError):
        policy(
            modes=(
                DisplayMode(1920, 1080, 241),
            ),
            preferred_mode=DisplayMode(
                1920, 1080, 241
            ),
        ).validate()


def test_preferred_mode_must_be_allowed():
    with pytest.raises(ValueError):
        policy(
            preferred_mode=DisplayMode(
                1280, 720, 120
            )
        ).validate()


def test_hdr_requires_10_bit():
    with pytest.raises(ValueError):
        policy(
            hdr_enabled=True,
            bit_depth=8,
            color_space="Rec.2020",
        ).validate()


def test_hdr_requires_rec2020():
    with pytest.raises(ValueError):
        policy(
            hdr_enabled=True,
            bit_depth=10,
            color_space="RGB",
        ).validate()


def test_render_preserves_exact_14_modes():
    payload = runtime_policy.render_settings_xml(
        TEMPLATE,
        policy(),
    )

    root = ET.fromstring(payload)

    found = tuple(
        DisplayMode(
            int(node.findtext("width")),
            int(node.findtext("height")),
            int(node.findtext("refresh_rate")),
        )
        for node in root.findall(
            "./resolutions/resolution"
        )
    )

    assert found == EXPECTED_14


def test_atomic_apply_and_state(tmp_path):
    result = runtime_policy.apply_policy_atomic(
        template=TEMPLATE,
        target_root=tmp_path,
        policy=policy(),
    )

    target = (
        tmp_path
        / runtime_policy.SETTINGS_NAME
    )

    assert target.exists()
    assert modes_from(target) == EXPECTED_14
    assert result["mode_count"] == 14
    assert result["policy_version"] == "kg008-k22-test-v1"

    assert (
        tmp_path
        / runtime_policy.STATE_NAME
    ).exists()


def test_second_apply_preserves_last_known_good(
    tmp_path,
):
    first = policy()

    runtime_policy.apply_policy_atomic(
        template=TEMPLATE,
        target_root=tmp_path,
        policy=first,
    )

    first_bytes = (
        tmp_path
        / runtime_policy.SETTINGS_NAME
    ).read_bytes()

    second_modes = (
        DisplayMode(1920, 1080, 60),
        DisplayMode(1920, 1080, 120),
    )

    second = policy(
        policy_version="kg008-k22-test-v2",
        modes=second_modes,
        preferred_mode=DisplayMode(
            1920, 1080, 120
        ),
    )

    runtime_policy.apply_policy_atomic(
        template=TEMPLATE,
        target_root=tmp_path,
        policy=second,
    )

    assert (
        tmp_path
        / runtime_policy.LKG_NAME
    ).read_bytes() == first_bytes

    assert modes_from(
        tmp_path
        / runtime_policy.SETTINGS_NAME
    ) == second_modes


def test_restore_last_known_good(tmp_path):
    runtime_policy.apply_policy_atomic(
        template=TEMPLATE,
        target_root=tmp_path,
        policy=policy(),
    )

    second = policy(
        policy_version="kg008-k22-test-v2",
        modes=(
            DisplayMode(1920, 1080, 60),
        ),
        preferred_mode=DisplayMode(
            1920, 1080, 60
        ),
    )

    runtime_policy.apply_policy_atomic(
        template=TEMPLATE,
        target_root=tmp_path,
        policy=second,
    )

    runtime_policy.restore_last_known_good(
        tmp_path
    )

    assert modes_from(
        tmp_path
        / runtime_policy.SETTINGS_NAME
    ) == EXPECTED_14


def test_no_driver_rebuild_dependency():
    text = MODULE.read_text(encoding="utf-8")

    assert "Driver.cpp" not in text
    assert "msbuild" not in text.lower()
    assert "pnputil" not in text.lower()
