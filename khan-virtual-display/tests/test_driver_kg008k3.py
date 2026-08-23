import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DRIVER = ROOT / "driver" / "KhanVirtualDisplay"


def read(path):
    return path.read_text(encoding="utf-8", errors="ignore")


def test_driver_source_exists():
    required = {
        "Driver.cpp",
        "Driver.h",
        "Trace.h",
        "KhanModes.h",
        "KhanVirtualDisplay.inf",
        "KhanVirtualDisplay.vcxproj",
    }

    actual = {p.name for p in DRIVER.iterdir() if p.is_file()}

    assert required <= actual


def test_canonical_seven_modes():
    text = read(DRIVER / "KhanModes.h")

    expected = {
        (3840, 2160, 60),
        (2560, 1440, 120),
        (2560, 1440, 60),
        (1920, 1080, 120),
        (1920, 1080, 60),
        (1280, 720, 60),
        (1280, 720, 30),
    }

    found = {
        tuple(map(int, match))
        for match in re.findall(
            r"\{\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,",
            text,
        )
    }

    assert expected == found


def test_hdr_architecture_contract():
    text = read(DRIVER / "KhanModes.h")

    assert "HdrArchitectureEnabled = true" in text
    assert "HdrBitsPerComponent = 10" in text

    design = read(ROOT / "driver" / "HDR-DESIGN.md")

    assert "SDR must always remain available" in design
    assert "10 bits per component" in design
    assert "Dolby Vision is not part of KG-008K3" in design


def test_khan_identity_is_present():
    cpp = read(DRIVER / "Driver.cpp")

    assert "Khan Virtual Display" in cpp
    assert "Khan Cloud Virtual Monitor" in cpp


def test_single_initial_monitor():
    cpp = read(DRIVER / "Driver.cpp")

    assert re.search(
        r"IDD_SAMPLE_MONITOR_COUNT\s*=\s*1\s*;",
        cpp,
    )


def test_iddcx_lifecycle_preserved():
    cpp = read(DRIVER / "Driver.cpp")

    required = (
        "IddCxDeviceInitialize",
        "IddCxAdapterInitAsync",
        "IddCxMonitorCreate",
        "IddCxMonitorArrival",
        "IddCxSwapChainSetDevice",
        "IddCxSwapChainReleaseAndAcquireBuffer",
        "IddCxSwapChainFinishedProcessingFrame",
    )

    for symbol in required:
        assert symbol in cpp


def test_vdd_code_not_imported():
    mapping = json.loads(
        (ROOT / "upstream" / "source-map.json").read_text(
            encoding="utf-8"
        )
    )

    assert (
        mapping["virtualdrivers"]["code_imported_in_kg008k3"]
        is False
    )


def test_ms_derived_files_recorded():
    mapping = json.loads(
        (ROOT / "upstream" / "source-map.json").read_text(
            encoding="utf-8"
        )
    )

    derived = mapping["microsoft"]["derived_files"]

    assert len(derived) >= 5

    destinations = {entry["khan"] for entry in derived}

    assert (
        "driver/KhanVirtualDisplay/Driver.cpp"
        in destinations
    )


def test_driver_is_image_build_artifact():
    artifact = json.loads(
        (
            ROOT
            / "installer"
            / "artifact-template.json"
        ).read_text(encoding="utf-8")
    )

    assert artifact["source"]["type"] == "khan_artifact"
    assert artifact["stage"] == "image_build"


def _read_khan_inf():
    raw = (
        DRIVER / "KhanVirtualDisplay.inf"
    ).read_bytes()

    assert raw.startswith(b"\xff\xfe")

    text = raw.decode("utf-16")

    assert "\ufffd" not in text

    return text


def test_windows_driver_inf_contract():
    text = _read_khan_inf()

    required = (
        "Class = Display",
        "{4D36E968-E325-11CE-BFC1-08002BE10318}",
        "Provider=%ManufacturerName%",
        "CatalogFile=KhanVirtualDisplay.cat",
        "DriverVer=08/23/2026,0.1.0.0",
        r"Root\KhanCloudVirtualDisplay",
        "UmdfService=KhanVirtualDisplay,"
        "KhanVirtualDisplay_Install",
        "UmdfServiceOrder=KhanVirtualDisplay",
        "[KhanVirtualDisplay_Install]",
        r"ServiceBinary=%12%\UMDF\KhanVirtualDisplay.dll",
        "KhanVirtualDisplay.dll=1",
        'ManufacturerName="Khan Cloud"',
        'DiskName = "Khan Virtual Display Driver"',
        'DeviceName="Khan Virtual Display"',
        '"IndirectKmd"',
    )

    for token in required:
        assert token in text


def test_windows_driver_inf_has_no_install_critical_sample_identity():
    text = _read_khan_inf()

    forbidden = (
        "IddSampleDriver.cat",
        r"Root\IddSampleDriver",
        "IddSampleDriverGroup",
        "UmdfService=IddSampleDriver",
        r"ServiceBinary=%12%\UMDF\IddSampleDriver.dll",
        "IddSampleDriver.dll=1",
        "<Your manufacturer name>",
        'DeviceName="IddSampleDriver Device"',
    )

    for token in forbidden:
        assert token not in text


def test_windows_resource_has_khan_identity():
    text = read(DRIVER / "KhanVirtualDisplay.rc")

    assert '"KhanVirtualDisplay"' in text
    assert '"KhanVirtualDisplay.dll"' in text
    assert "IddSampleDriver" not in text


def test_all_microsoft_derived_build_files_have_provenance():
    mapping = json.loads(
        (
            ROOT
            / "upstream"
            / "source-map.json"
        ).read_text(encoding="utf-8")
    )

    pairs = {
        (
            item["upstream"],
            item["khan"],
        )
        for item in mapping["microsoft"]["derived_files"]
    }

    required = {
        (
            "video/IndirectDisplay/IddSampleDriver/Driver.cpp",
            "driver/KhanVirtualDisplay/Driver.cpp",
        ),
        (
            "video/IndirectDisplay/IddSampleDriver/Driver.h",
            "driver/KhanVirtualDisplay/Driver.h",
        ),
        (
            "video/IndirectDisplay/IddSampleDriver/Trace.h",
            "driver/KhanVirtualDisplay/Trace.h",
        ),
        (
            "video/IndirectDisplay/IddSampleDriver/IddSampleDriver.inf",
            "driver/KhanVirtualDisplay/KhanVirtualDisplay.inf",
        ),
        (
            "video/IndirectDisplay/IddSampleDriver/IddSampleDriver.vcxproj",
            "driver/KhanVirtualDisplay/KhanVirtualDisplay.vcxproj",
        ),
        (
            "video/IndirectDisplay/IddSampleDriver/IddSampleDriver.vcxproj.filters",
            "driver/KhanVirtualDisplay/KhanVirtualDisplay.vcxproj.filters",
        ),
        (
            "video/IndirectDisplay/IddSampleDriver/IddSampleDriver.rc",
            "driver/KhanVirtualDisplay/KhanVirtualDisplay.rc",
        ),
    }

    assert pairs == required


def test_windows_resource_is_part_of_visual_studio_build():
    project = read(
        DRIVER / "KhanVirtualDisplay.vcxproj"
    )

    filters = read(
        DRIVER / "KhanVirtualDisplay.vcxproj.filters"
    )

    assert (
        'ResourceCompile Include="KhanVirtualDisplay.rc"'
        in project
    )

    assert "KhanVirtualDisplay.rc" in filters

    assert "IddSampleDriver.rc" not in project
    assert "IddSampleDriver.rc" not in filters


def test_visual_studio_project_requires_cpp17():
    from pathlib import Path
    import xml.etree.ElementTree as ET

    project = (
        Path(__file__).resolve().parents[1]
        / "driver"
        / "KhanVirtualDisplay"
        / "KhanVirtualDisplay.vcxproj"
    )

    namespace = {
        "m": "http://schemas.microsoft.com/developer/msbuild/2003"
    }

    root = ET.parse(project).getroot()

    configurations = []

    for group in root.findall("m:ItemDefinitionGroup", namespace):
        compiler = group.find("m:ClCompile", namespace)

        if compiler is None:
            continue

        language = compiler.find(
            "m:LanguageStandard",
            namespace,
        )

        configurations.append(
            None if language is None else language.text
        )

    assert len(configurations) == 4
    assert configurations == ["stdcpp17"] * 4



def test_compiled_resource_branding_contract():
    rc = read(DRIVER / "KhanVirtualDisplay.rc")

    required = (
        '"Khan Virtual Display Driver"',
        '"KhanVirtualDisplay"',
        '"KhanVirtualDisplay.dll"',
        '"Khan Cloud Virtual Display"',
        '"Khan Cloud"',
        '"0.1.0.0"',
    )

    for token in required:
        assert token in rc

    forbidden = (
        "UMDF Indirect Display Driver Sample",
        "Windows (R) Win 7 DDK driver",
        "Windows (R) Win 7 DDK provider",
        "IddSampleDriver",
    )

    for token in forbidden:
        assert token not in rc
