from pathlib import Path
import json
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
DRV = ROOT / "driver" / "KhanVirtualDisplay"

def read(path):
    return path.read_text(encoding="utf-8-sig")

def test_kg008k6_mit_core_identity_and_policy():
    cpp = read(DRV / "Driver.cpp")
    # Driver.cpp is inspected as C++ source text, so Windows
    # backslashes appear escaped in the source representation.
    assert r'\\\\.\\pipe\\KhanCloudVirtualDisplay' in cpp
    assert r'C:\\ProgramData\\KhanCloud\\VirtualDisplay' in cpp
    assert r'SOFTWARE\\KhanCloud\\VirtualDisplay' in cpp
    for forbidden in ("MTTVirtualDisplayPipe", "C:\\VirtualDisplayDriver", "MikeTheTech"):
        assert forbidden not in cpp

def test_kg008k6_inf_contract():
    raw = (DRV / "KhanVirtualDisplay.inf").read_bytes()
    assert raw.startswith(b"\xff\xfe")
    text = raw.decode("utf-16")
    for token in (
        r"Root\KhanCloudVirtualDisplay",
        "CatalogFile=KhanVirtualDisplay.cat",
        "UmdfService=KhanVirtualDisplay,KhanVirtualDisplay_Install",
        r"ServiceBinary=%13%\KhanVirtualDisplay.dll",
        'ManufacturerName="Khan Cloud"',
        'DeviceName="Khan Virtual Display"',
    ):
        assert token in text
    for forbidden in ("MttVDD", "MikeTheTech"):
        assert forbidden not in text

def test_kg008k6_project_is_cpp17_and_iddcx_110():
    text = read(DRV / "KhanVirtualDisplay.vcxproj")
    assert "<TargetName>KhanVirtualDisplay</TargetName>" in text
    assert "KhanVirtualDisplay.inf" in text
    assert "KhanVirtualDisplay.rc" in text
    assert text.count("<LanguageStandard>stdcpp17</LanguageStandard>") >= 4
    assert "<IDDCX_VERSION_MINOR>10</IDDCX_VERSION_MINOR>" in text

def test_kg008k6_exact_seven_modes():
    cfg = ROOT / "config" / "khan-vdd-settings.xml"
    tree = ET.parse(cfg)
    modes = []
    for r in tree.findall(".//resolutions/resolution"):
        modes.append((
            int(r.findtext("width")),
            int(r.findtext("height")),
            int(float(r.findtext("refresh_rate"))),
        ))
    assert modes == [
        (3840, 2160, 60),
        (2560, 1440, 120),
        (2560, 1440, 60),
        (1920, 1080, 120),
        (1920, 1080, 60),
        (1280, 720, 60),
        (1280, 720, 30),
    ]
    assert not tree.findall(".//global/g_refresh_rate")

def test_kg008k6_hdr_architecture_enabled():
    tree = ET.parse(ROOT / "config" / "khan-vdd-settings.xml")
    assert tree.findtext(".//hdr10_static_metadata/enabled") == "true"
    assert tree.findtext(".//color_primaries/enabled") == "true"
    assert tree.findtext(".//color_space/enabled") == "true"
    assert tree.findtext(".//force_bit_depth") == "10"

def test_kg008k6_provenance():
    data = json.loads((ROOT / "upstream" / "source-map-kg008k6.json").read_text())
    assert data["upstreams"][0]["commit"] == "d7244969b2aa8bb38e76d79505eda217996cefea"
    assert data["upstreams"][0]["license"] == "MIT"
    assert data["policy"]["canonical_mode_count"] == 7

def test_kg008k6_inf_windows_byte_contract():
    raw = (DRV / "KhanVirtualDisplay.inf").read_bytes()

    assert raw.startswith(b"\xff\xfe")

    text = raw[2:].decode("utf-16le")

    # Windows INF parser requires real line/section structure.
    assert text.count("\r\n") >= 60
    assert "\n" not in text.replace("\r\n", "")
    assert "\r" not in text.replace("\r\n", "")

    assert "[Version]\r\n" in text
    assert 'Signature="$Windows NT$"\r\n' in text
    assert "[Manufacturer]\r\n" in text
    assert r"Root\KhanCloudVirtualDisplay" in text

    lines = text.split("\r\n")

    assert "[Version]" in lines
    assert "[Manufacturer]" in lines
    assert "[MyDevice_Install.NT]" in lines
    assert "[MyDevice_Install.NT.Wdf]" in lines
    assert "[KhanVirtualDisplay_Install]" in lines

def test_kg008k6_driver_store_dirid13_contract():
    raw = (DRV / "KhanVirtualDisplay.inf").read_bytes()

    assert raw.startswith(b"\xff\xfe")

    text = raw[2:].decode("utf-16le")

    assert "UMDriverCopy=13\r\n" in text
    assert "UMDriverCopy=12,UMDF" not in text
    assert "[UMDriverCopy]\r\n" in text
    assert "KhanVirtualDisplay.dll\r\n" in text



def test_kg008k10_umdf_service_binary_runs_from_driver_store():
    from pathlib import Path

    inf_path = (
        Path(__file__).resolve().parents[1] /
        "driver/KhanVirtualDisplay/KhanVirtualDisplay.inf"
    )

    raw = inf_path.read_bytes()

    assert raw.startswith(b"\xff\xfe")

    text = raw[2:].decode("utf-16-le")

    assert "UMDriverCopy=13" in text
    assert r"ServiceBinary=%13%\KhanVirtualDisplay.dll" in text
    assert r"ServiceBinary=%12%\UMDF\KhanVirtualDisplay.dll" not in text
