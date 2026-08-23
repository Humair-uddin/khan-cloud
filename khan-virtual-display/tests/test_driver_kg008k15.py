import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "khan-vdd-settings.xml"
DRIVER = (
    ROOT
    / "driver"
    / "KhanVirtualDisplay"
    / "Driver.cpp"
)


EXPECTED_MODES = [
    # K13 baseline
    (3840, 2160, 60),
    (2560, 1440, 120),
    (2560, 1440, 60),
    (1920, 1080, 120),
    (1920, 1080, 60),
    (1280, 720, 60),
    (1280, 720, 30),

    # K15 high-refresh expansion
    (3840, 2160, 120),

    (2560, 1440, 240),
    (2560, 1440, 165),
    (2560, 1440, 144),

    (1920, 1080, 240),
    (1920, 1080, 165),
    (1920, 1080, 144),
]


def _config_root():
    return ET.parse(CONFIG).getroot()


def _modes():
    root = _config_root()

    return [
        (
            int(node.findtext("width")),
            int(node.findtext("height")),
            int(node.findtext("refresh_rate")),
        )
        for node in root.findall(".//resolution")
    ]


def test_kg008k15_exact_fourteen_mode_policy():
    modes = _modes()

    assert modes == EXPECTED_MODES
    assert len(modes) == 14
    assert len(set(modes)) == 14


def test_kg008k15_preserves_k13_seven_mode_baseline():
    assert _modes()[:7] == EXPECTED_MODES[:7]


def test_kg008k15_high_refresh_modes_are_exact():
    modes = set(_modes())

    required = {
        (3840, 2160, 120),
        (2560, 1440, 240),
        (2560, 1440, 165),
        (2560, 1440, 144),
        (1920, 1080, 240),
        (1920, 1080, 165),
        (1920, 1080, 144),
    }

    assert required <= modes


def test_kg008k15_no_4k_refresh_above_120():
    modes = _modes()

    four_k = [
        refresh
        for width, height, refresh in modes
        if width == 3840 and height == 2160
    ]

    assert sorted(four_k) == [60, 120]


def test_kg008k15_refresh_policy_ceiling_is_240():
    root = _config_root()

    assert (
        root.findtext(
            ".//edid_mode_filtering/max_refresh_rate"
        )
        == "240"
    )


def test_kg008k15_manual_policy_remains_authoritative():
    root = _config_root()

    assert root.findtext(
        ".//auto_resolutions/enabled"
    ) == "false"

    assert root.findtext(
        ".//auto_resolutions/source_priority"
    ) == "manual"


def test_kg008k15_driver_accepts_240hz_policy_range():
    text = DRIVER.read_text()

    # Existing production validation allows refresh ceilings
    # through 300 Hz, therefore the 240 Hz policy is valid.
    assert (
        "if (minRefresh <= 0 || minRefresh > 300)"
        in text
    )

    assert (
        "float_to_vsync(stof(refreshRate), "
        "vsync_num, vsync_den);"
        in text
    )


def test_kg008k15_runtime_tuple_semantics_unchanged():
    text = DRIVER.read_text()

    assert (
        "res.push_back("
        "make_tuple(stoi(width), stoi(height), "
        "vsync_num, vsync_den));"
        in text
    )

    assert "static double ModeRefreshHz(" in text
    assert "static bool SameRuntimeMode(" in text
