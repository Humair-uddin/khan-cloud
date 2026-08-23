from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]

CPP_PATH = (
    ROOT /
    "driver" /
    "KhanVirtualDisplay" /
    "Driver.cpp"
)

CFG_PATH = (
    ROOT /
    "config" /
    "khan-vdd-settings.xml"
)


def cpp():
    return CPP_PATH.read_text(
        encoding="utf-8-sig"
    )


def hardcoded_edid():
    text = cpp()

    m = re.search(
        r"vector<BYTE>\s+hardcodedEdid\s*=\s*\{(.*?)\};",
        text,
        re.S,
    )

    assert m

    data = bytes(
        int(x, 16)
        for x in re.findall(
            r"0x([0-9a-fA-F]{2})",
            m.group(1)
        )
    )

    assert len(data) == 256

    return data


def cta_extended_block(tag):
    edid = hardcoded_edid()

    ext = edid[128:256]

    assert ext[0] == 0x02
    assert sum(ext) % 256 == 0

    end = ext[2] if ext[2] else 127
    i = 4

    while i < end:
        header = ext[i]
        block_tag = header >> 5
        length = header & 0x1f
        payload = ext[i + 1:i + 1 + length]

        if (
            block_tag == 7 and
            payload and
            payload[0] == tag
        ):
            return payload

        i += 1 + length

    raise AssertionError(
        f"CTA extended block 0x{tag:02X} absent"
    )


def test_k16_hdr10_cta_contract():
    payload = cta_extended_block(0x06)

    assert len(payload) >= 3

    eotf = payload[1]
    static_metadata = payload[2]

    # SDR + SMPTE ST2084/PQ.
    assert eotf & 0x01
    assert eotf & 0x04

    # Khan production contract does not yet claim HLG.
    assert not (eotf & 0x08)

    # Static Metadata Descriptor Type 1.
    assert static_metadata & 0x01


def test_k16_bt2020_rgb_and_ycc_contract():
    payload = cta_extended_block(0x05)

    assert len(payload) >= 2

    flags = payload[1]

    assert flags & 0x40  # BT.2020 YCC
    assert flags & 0x80  # BT.2020 RGB


def test_k16_windows_hdr_runtime_callbacks_registered():
    text = cpp()

    for token in (
        "EvtIddCxAdapterQueryTargetInfo",
        "EvtIddCxMonitorSetDefaultHdrMetaData",
        "EvtIddCxParseMonitorDescription2",
        "EvtIddCxMonitorQueryTargetModes2",
        "EvtIddCxAdapterCommitModes2",
    ):
        assert token in text


def test_k16_target_caps_are_wcg_and_high_color():
    text = cpp()

    start = text.index(
        "NTSTATUS "
        "VirtualDisplayDriverEvtIddCxAdapterQueryTargetInfo("
    )

    end = text.index(
        "NTSTATUS "
        "VirtualDisplayDriverEvtIddCxMonitorSetDefaultHdrMetadata(",
        start,
    )

    body = text[start:end]

    assert (
        "IDDCX_TARGET_CAPS_WIDE_COLOR_SPACE"
        in body
    )

    assert (
        "IDDCX_TARGET_CAPS_HIGH_COLOR_SPACE"
        in body
    )

    assert "DitheringSupport = {}" in body


def test_k16_native_rgb_8_and_10_bpc_are_advertised():
    text = cpp()

    assert (
        "SDRCOLOUR = "
        "IDDCX_BITS_PER_COMPONENT_8"
        in text
    )

    assert (
        "HDRCOLOUR = "
        "IDDCX_BITS_PER_COMPONENT_10"
        in text
    )

    assert (
        "Mode.BitsPerComponent.Rgb = "
        "SDRCOLOUR | HDRCOLOUR"
        in text
    )


def test_k16_windows_hdr10_metadata_is_consumed():
    text = cpp()

    for token in (
        "IDDCX_HDRMETADATA_TYPE_HDR10",
        "pInArgs->Data.pHdr10",
        "state.DefaultMetadata",
        "state.HasDefaultMetadata = true",
        "IDDCX_METADATA2_VALID_FLAGS_HDR10METADATA",
        "IDDCX_HDR10_FRAME_METADATA_TYPE_DEFAULT",
        "IDDCX_HDR10_FRAME_METADATA_TYPE_UNCHANGED",
        "IDDCX_HDR10_FRAME_METADATA_TYPE_NEW",
        "frameHdr.NewMetaData",
    ):
        assert token in text


def test_k16_production_config_requests_hdr10_rec2020():
    import xml.etree.ElementTree as ET

    tree = ET.parse(CFG_PATH)

    assert (
        tree.findtext(
            ".//hdr10_static_metadata/enabled"
        )
        == "true"
    )

    assert (
        tree.findtext(
            ".//color_primaries/enabled"
        )
        == "true"
    )

    assert (
        tree.findtext(
            ".//primary_color_space"
        )
        == "Rec.2020"
    )

    assert (
        tree.findtext(
            ".//force_bit_depth"
        )
        == "10"
    )

def test_k16_gamma_capability_is_truthful():
    text = cpp()

    assert (
        "GammaSupport = "
        "IDDCX_FEATURE_IMPLEMENTATION_NONE;"
        in text
    )

    assert (
        "IddConfig.EvtIddCxMonitorSetGammaRamp = "
        "VirtualDisplayDriverEvtIddCxMonitorSetGammaRamp;"
        in text
    )

    assert (
        "3x4 matrix transform applied successfully"
        not in text
    )

    assert (
        "RGB gamma ramp applied successfully"
        not in text
    )


def test_k16_legacy_gamma_callback_fails_closed():
    text = cpp()

    start = text.index(
        "NTSTATUS "
        "VirtualDisplayDriverEvtIddCxMonitorSetGammaRamp("
    )

    end = text.index(
        "#pragma endregion",
        start,
    )

    body = text[start:end]

    assert "UNREFERENCED_PARAMETER(MonitorObject);" in body
    assert "UNREFERENCED_PARAMETER(pInArgs);" in body
    assert "return STATUS_NOT_SUPPORTED;" in body

def test_k16_production_settings_are_single_hdr_authority():
    import xml.etree.ElementTree as ET

    root = ET.parse(CFG_PATH).getroot()

    integration = root.find(".//edid_integration")

    assert integration is not None

    assert integration.findtext("enabled") == "false"

    assert (
        integration.findtext(
            "auto_configure_from_edid"
        )
        == "false"
    )

    assert (
        integration.findtext(
            "override_manual_settings"
        )
        == "false"
    )

    assert (
        root.findtext(".//primary_color_space")
        == "Rec.2020"
    )

    assert root.findtext(".//force_bit_depth") == "10"


def test_k16_edid_profile_requires_explicit_double_gate():
    text = cpp()

    gate = (
        "if (edidIntegrationEnabled && "
        "autoConfigureFromEdid)"
    )

    assert gate in text

    apply_pos = text.index(
        "ApplyEdidProfile(edidProfile)"
    )

    gate_pos = text.rfind(
        gate,
        0,
        apply_pos,
    )

    assert gate_pos != -1


def test_k16_inactive_profile_cannot_silently_become_authority():
    import xml.etree.ElementTree as ET

    root = ET.parse(CFG_PATH).getroot()

    integration = root.find(".//edid_integration")

    assert integration.findtext("enabled") == "false"
    assert (
        integration.findtext(
            "auto_configure_from_edid"
        )
        == "false"
    )


def test_k16_gamma_registration_required_for_iddcx_init():
    text = cpp()

    assert (
        "IddConfig.EvtIddCxMonitorSetGammaRamp = "
        "VirtualDisplayDriverEvtIddCxMonitorSetGammaRamp;"
        in text
    )

    assert (
        "GammaSupport = "
        "IDDCX_FEATURE_IMPLEMENTATION_NONE;"
        in text
    )

    start = text.index(
        "NTSTATUS "
        "VirtualDisplayDriverEvtIddCxMonitorSetGammaRamp("
    )

    end = text.index(
        "#pragma endregion",
        start,
    )

    body = text[start:end]

    assert "return STATUS_NOT_SUPPORTED;" in body
