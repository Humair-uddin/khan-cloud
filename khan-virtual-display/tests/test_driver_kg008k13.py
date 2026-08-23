from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]

DRIVER = (
    ROOT
    / "driver"
    / "KhanVirtualDisplay"
    / "Driver.cpp"
)


def driver_text():
    return DRIVER.read_text()


def hardcoded_edid():
    text = driver_text()

    match = re.search(
        r"vector<BYTE>\s+hardcodedEdid\s*=\s*\{"
        r"(.*?)"
        r"\};",
        text,
        re.S,
    )

    assert match is not None

    values = [
        int(token, 16)
        for token in re.findall(
            r"0x([0-9a-fA-F]{2})",
            match.group(1),
        )
    ]

    assert len(values) == 256

    return bytes(values)


def decode_manufacturer(edid):
    value = (edid[8] << 8) | edid[9]

    letters = []

    for shift in (10, 5, 0):
        code = (value >> shift) & 0x1F
        assert 1 <= code <= 26
        letters.append(chr(ord("A") + code - 1))

    return "".join(letters)


def test_kg008k13_hardcoded_edid_has_khan_identity():
    edid = hardcoded_edid()

    assert decode_manufacturer(edid) == "KHC"

    product = edid[10] | (edid[11] << 8)

    assert product == 0x0001

    descriptor = edid[108:126]

    assert descriptor[:5] == bytes(
        [0x00, 0x00, 0x00, 0xFC, 0x00]
    )

    assert descriptor[5:18] == b"KhanCloud VDD"

    assert sum(edid[:128]) % 256 == 0


def test_kg008k13_runtime_rewrite_matches_base_identity():
    text = driver_text()

    expected = (
        r"edid\s*\[\s*8\s*\]\s*=\s*0x2d\s*;"
        r".*?"
        r"edid\s*\[\s*9\s*\]\s*=\s*0x03\s*;"
        r".*?"
        r"edid\s*\[\s*10\s*\]\s*=\s*0x01\s*;"
        r".*?"
        r"edid\s*\[\s*11\s*\]\s*=\s*0x00\s*;"
    )

    assert re.search(expected, text, re.S)

    for legacy in (
        r"edid\s*\[\s*8\s*\]\s*=\s*0x36\s*;",
        r"edid\s*\[\s*9\s*\]\s*=\s*0x94\s*;",
        r"edid\s*\[\s*10\s*\]\s*=\s*0x37\s*;",
        r"edid\s*\[\s*11\s*\]\s*=\s*0x13\s*;",
    ):
        assert re.search(legacy, text) is None


def test_kg008k13_legacy_mtt_identity_is_absent():
    edid = hardcoded_edid()
    text = driver_text()

    assert b"VDD by MTT" not in edid
    assert b"MTT" not in edid
    assert "VDD by MTT" not in text

    assert decode_manufacturer(edid) == "KHC"
    assert edid[10:12] == bytes([0x01, 0x00])


def test_kg008k13_runtime_configuration_root_is_programdata():
    text = driver_text()

    assert (
        'wstring confpath = '
        'L"C:\\\\ProgramData\\\\KhanCloud\\\\VirtualDisplay";'
        in text
    )


def test_kg008k13_canonical_seven_mode_policy():
    import xml.etree.ElementTree as ET

    config = (
        ROOT
        / "config"
        / "khan-vdd-settings.xml"
    )

    root = ET.parse(config).getroot()

    modes = []

    for node in root.findall(".//resolution"):
        modes.append(
            (
                int(node.findtext("width")),
                int(node.findtext("height")),
                int(node.findtext("refresh_rate")),
            )
        )

    # K13 proved these seven modes through Windows runtime
    # enumeration and activation. Preserve them as the baseline;
    # later batches may append higher-refresh capabilities.
    assert modes[:7] == [
        (3840, 2160, 60),
        (2560, 1440, 120),
        (2560, 1440, 60),
        (1920, 1080, 120),
        (1920, 1080, 60),
        (1280, 720, 60),
        (1280, 720, 30),
    ]


def test_kg008k13_build_contains_runtime_seed_bundle():
    project = (
        ROOT
        / "driver"
        / "KhanVirtualDisplay"
        / "KhanVirtualDisplay.vcxproj"
    ).read_text()

    assert project.count(
        r'if not exist "$(TargetDir)\KhanVirtualDisplay\RuntimeConfig\EDID"'
    ) == 4

    assert project.count(
        r'mkdir "$(TargetDir)\KhanVirtualDisplay\RuntimeConfig\EDID"'
    ) == 4

    assert project.count(
        r'"$(TargetDir)\KhanVirtualDisplay\RuntimeConfig\khan-vdd-settings.xml"'
    ) == 4

    assert project.count(
        r'"$(TargetDir)\KhanVirtualDisplay\RuntimeConfig\EDID\monitor_profile.xml"'
    ) == 4

    assert r'$(TargetDir)\RuntimeConfig' not in project

    assert (
        r'<Xml Include="..\..\config\EDID\monitor_profile.xml" />'
        in project
    )


def test_kg008k13_mutable_config_is_not_installed_to_driverstore():
    inf = (
        ROOT
        / "driver"
        / "KhanVirtualDisplay"
        / "KhanVirtualDisplay.inf"
    )

    raw = inf.read_bytes()

    assert raw.startswith(b"\xff\xfe")

    text = raw[2:].decode("utf-16-le")

    assert "khan-vdd-settings.xml" not in text
    assert "monitor_profile.xml" not in text

    assert "UMDriverCopy=13" in text
    assert (
        r"ServiceBinary=%13%\KhanVirtualDisplay.dll"
        in text
    )


def test_edid_generated_modes_are_normalized_to_runtime_vsync_tuple():
    """
    EDID profile modes are stored as
    (width, height, multiplier, nominal_refresh).

    They must be converted before entering monitorModes because every IddCx
    callback consumes monitorModes as
    (width, height, VSyncNumerator, VSyncDenominator).
    """
    text = DRIVER.read_text()

    assert (
        "const double refreshRate =" in text
    )
    assert (
        "static_cast<double>(nominalRefreshRate) *" in text
    )
    assert (
        "static_cast<double>(refreshRateMultiplier) / 1000.0"
        in text
    )
    assert (
        "float_to_vsync(" in text
    )
    assert (
        "make_tuple(width, height, vsyncNum, vsyncDen)"
        in text
    )

    assert "generatedModes.push_back(mode);" not in text


def test_edid_profile_representation_remains_distinct_from_runtime_modes():
    """
    Preserve raw EDID multiplier/nominal values while loading the profile;
    normalization belongs at the EDID -> runtime mode boundary.
    """
    text = DRIVER.read_text()

    assert (
        "profile.modes.push_back("
        "make_tuple(tempWidth, tempHeight, "
        "tempRefreshRateMultiplier, "
        "tempNominalRefreshRate))"
        in text
    )

    assert (
        "generatedModes.push_back("
        in text
    )

    assert (
        "make_tuple(width, height, vsyncNum, vsyncDen)"
        in text
    )


def test_kg008k13_canonical_vsync_mode_identity():
    driver = (
        ROOT
        / "driver"
        / "KhanVirtualDisplay"
        / "Driver.cpp"
    ).read_text()

    assert "static double ModeRefreshHz(" in driver
    assert "static bool SameRuntimeMode(" in driver

    assert "SameRuntimeMode(edidMode, manualMode)" in driver
    assert "SameRuntimeMode(mode, preferredMode)" in driver
    assert "SameRuntimeMode(a, b)" in driver

    assert (
        "get<3>(edidMode) == get<3>(manualMode)"
        not in driver
    )

    assert (
        "get<3>(mode) == get<3>(preferredMode)"
        not in driver
    )

    assert (
        'ModeRefreshHz(preferredMode) << "Hz'
        in driver
    )


def test_kg008k13_final_mode_semantics_cleanup():
    driver = (
        ROOT
        / "driver"
        / "KhanVirtualDisplay"
        / "Driver.cpp"
    ).read_text()

    for token in (
        "make_tuple(1920, 1080, 60, 1)",
        "make_tuple(1366, 768, 60, 1)",
        "make_tuple(1280, 720, 60, 1)",
        "make_tuple(800, 600, 60, 1)",
        "refreshRateCount[ModeRefreshHz(mode)]++;",
    ):
        assert token in driver

    for token in (
        "make_tuple(1920, 1080, 60, 0)",
        "make_tuple(1366, 768, 60, 0)",
        "make_tuple(1280, 720, 60, 0)",
        "make_tuple(800, 600, 60, 0)",
        'VSync = " << std::get<2>(monitorModes[i])',
        'RefreshRate: " << std::get<2>(mode)',
        'RefreshRate: " << std::get<2>(monitorModes[i])',
    ):
        assert token not in driver

def test_canonical_mode_helpers_are_declared_before_first_use():
    text = DRIVER.read_text()

    float_decl = text.index(
        "void float_to_vsync(float refresh_rate, int& num, int& den);"
    )
    float_call = text.index("float_to_vsync(", float_decl + 1)
    float_definition = text.index(
        "void float_to_vsync(float refresh_rate, int& num, int& den) {"
    )

    mode_decl = text.index(
        "static double ModeRefreshHz(\n"
        "    const tuple<int, int, int, int>& mode);"
    )
    mode_call = text.index("ModeRefreshHz(a)", mode_decl + 1)
    mode_definition = text.index(
        "static double ModeRefreshHz(\n"
        "    const tuple<int, int, int, int>& mode) {"
    )

    assert float_decl < float_call < float_definition
    assert mode_decl < mode_call < mode_definition

    assert text.count(
        "void float_to_vsync(float refresh_rate, int& num, int& den);"
    ) == 1

    assert text.count(
        "void float_to_vsync(float refresh_rate, int& num, int& den) {"
    ) == 1
