from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DRV = ROOT / "driver" / "KhanVirtualDisplay"

CPP = (DRV / "Driver.cpp").read_text(
    encoding="utf-8-sig"
)

HDR = (DRV / "Driver.h").read_text(
    encoding="utf-8-sig"
)


def function_body(name, next_name):
    """
    Select the real NTSTATUS function definition rather than the
    EVT_IDD_CX_* forward declaration near the beginning of Driver.cpp.
    """
    start_token = f"NTSTATUS {name}("
    end_token = f"NTSTATUS {next_name}("

    start = CPP.index(start_token)
    end = CPP.index(end_token, start + len(start_token))

    return CPP[start:end]


def test_k7_swapchain_bound_to_monitor():
    assert "IDDCX_MONITOR m_Monitor;" in HDR
    assert "m_Monitor(Monitor)" in CPP
    assert "std::make_unique<SwapChainProcessor>" in CPP

    start = CPP.index(
        "std::make_unique<SwapChainProcessor>"
    )

    call = CPP[start:start + 300]

    assert "Monitor" in call
    assert "SwapChain" in call
    assert "Device" in call
    assert "NewFrameEvent" in call


def test_k7_windows_default_hdr_consumed():
    body = function_body(
        "VirtualDisplayDriverEvtIddCxMonitorSetDefaultHdrMetadata",
        "VirtualDisplayDriverEvtIddCxParseMonitorDescription2",
    )

    assert "IDDCX_HDRMETADATA_TYPE_HDR10" in body
    assert "pInArgs->Data.pHdr10" in body
    assert "state.DefaultMetadata" in body
    assert "state.HasDefaultMetadata = true" in body
    assert "UNREFERENCED_PARAMETER(pInArgs)" not in body


def test_k7_commit_modes2_tracks_windows_wire_format():
    body = function_body(
        "VirtualDisplayDriverEvtIddCxAdapterCommitModes2",
        "VirtualDisplayDriverEvtIddCxMonitorSetGammaRamp",
    )

    assert "pInArgs->PathCount" in body
    assert "IDDCX_PATH_FLAGS_ACTIVE" in body
    assert "path.WireFormatInfo" in body
    assert "state.CommittedWireFormat" in body
    assert "state.HasCommittedWireFormat" in body


def test_k7_frame_metadata_state_machine():
    for token in (
        "IDDCX_METADATA2_VALID_FLAGS_HDR10METADATA",
        "IDDCX_HDR10_FRAME_METADATA_TYPE_DEFAULT",
        "IDDCX_HDR10_FRAME_METADATA_TYPE_UNCHANGED",
        "IDDCX_HDR10_FRAME_METADATA_TYPE_NEW",
        "frameHdr.NewMetaData",
    ):
        assert token in CPP


def test_k7_default_and_dynamic_metadata_are_separate():
    assert "IDDCX_HDR10_METADATA DefaultMetadata" in CPP
    assert "IDDCX_HDR10_METADATA CurrentFrameMetadata" in CPP

    assert (
        "state.CurrentFrameMetadata ="
        in CPP
    )

    assert (
        "state.DefaultMetadata"
        in CPP
    )

    assert (
        "frameHdr.NewMetaData"
        in CPP
    )


def test_k7_does_not_fake_dithering_support():
    body = function_body(
        "VirtualDisplayDriverEvtIddCxAdapterQueryTargetInfo",
        "VirtualDisplayDriverEvtIddCxMonitorSetDefaultHdrMetadata",
    )

    assert "IDDCX_TARGET_CAPS_WIDE_COLOR_SPACE" in body
    assert "IDDCX_TARGET_CAPS_HIGH_COLOR_SPACE" in body
    assert "pOutArgs->DitheringSupport = {}" in body


def test_k7_runtime_state_contract():
    for token in (
        "struct KhanHdrRuntimeState",
        "HasDefaultMetadata",
        "HasCurrentFrameMetadata",
        "CommittedWireFormat",
        "HasCommittedWireFormat",
        "PathActive",
        "g_KhanHdrRuntimeState",
        "g_KhanHdrRuntimeMutex",
    ):
        assert token in CPP
