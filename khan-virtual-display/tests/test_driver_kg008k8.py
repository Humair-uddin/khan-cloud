from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]

CPP = (
    ROOT /
    "driver/KhanVirtualDisplay/Driver.cpp"
).read_text(
    encoding="utf-8-sig"
)


def real_monitor_create_position(start):
    match = re.search(
        r"\bIddCxMonitorCreate\s*\(",
        CPP[start:],
    )

    assert match is not None

    return start + match.start()


def test_k8_edid_capture_is_at_iddcx_boundary():
    anchor = (
        "MonitorInfo.MonitorDescription.pData = "
        "IndirectDeviceContext::s_KnownMonitorEdid.data();"
    )

    capture = "kg008k8-runtime-edid.bin"

    assert anchor in CPP
    assert capture in CPP

    anchor_pos = CPP.index(anchor)
    capture_pos = CPP.index(
        capture,
        anchor_pos,
    )
    create_pos = real_monitor_create_position(
        anchor_pos
    )

    assert anchor_pos < capture_pos < create_pos


def test_k8_capture_records_runtime_state():
    for token in (
        "KG008K8_IDDCX_BOUNDARY=YES",
        "CONF_PATH=",
        "CUSTOM_EDID=",
        "PREVENT_SPOOF=",
        "CEA_OVERRIDE=",
        "EDID_SIZE=",
        "EDID_ID_BYTES=",
        "EXTENSION_COUNT=",
        "FIRST_16=",
    ):
        assert token in CPP


def test_k8_capture_uses_actual_monitor_vector():
    assert (
        "const auto& runtimeEdid =\n"
        "                        "
        "IndirectDeviceContext::s_KnownMonitorEdid;"
        in CPP
    )


def test_k8_capture_precedes_real_monitor_create_call():
    capture_pos = CPP.index(
        "kg008k8-runtime-edid.bin"
    )

    create_pos = real_monitor_create_position(
        capture_pos
    )

    assert capture_pos < create_pos
