from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

CPP = (
    ROOT
    / "driver"
    / "KhanVirtualDisplay"
    / "Driver.cpp"
)

HDR = (
    ROOT
    / "driver"
    / "KhanVirtualDisplay"
    / "Driver.h"
)


def cpp():
    return CPP.read_text()


def hdr():
    return HDR.read_text()


def test_render_adapter_luid_state_is_atomic():
    text = hdr()

    assert (
        "std::atomic<LONG> "
        "m_LastRenderAdapterLuidHigh{0};"
        in text
    )

    assert (
        "std::atomic<ULONG> "
        "m_LastRenderAdapterLuidLow{0};"
        in text
    )


def test_assign_swapchain_records_render_adapter_luid():
    text = cpp()

    start = text.index(
        "void IndirectDeviceContext::"
        "AssignSwapChain("
    )

    end = text.index(
        "void IndirectDeviceContext::"
        "UnassignSwapChain(",
        start,
    )

    block = text[start:end]

    assert "RenderAdapter.HighPart" in block
    assert "RenderAdapter.LowPart" in block

    assert (
        "m_LastRenderAdapterLuidHigh.store("
        in block
    )

    assert (
        "m_LastRenderAdapterLuidLow.store("
        in block
    )


def test_lifecycle_api_returns_render_adapter_luid():
    text = hdr()

    assert (
        "LONG& RenderAdapterLuidHigh"
        in text
    )

    assert (
        "ULONG& RenderAdapterLuidLow"
        in text
    )


def test_lifecycle_snapshot_reads_render_adapter_luid():
    text = cpp()

    start = text.index(
        "void IndirectDeviceContext::"
        "GetSwapChainLifecycleTelemetry("
    )

    block = text[
        start:start + 2200
    ]

    assert (
        "m_LastRenderAdapterLuidHigh.load("
        in block
    )

    assert (
        "m_LastRenderAdapterLuidLow.load("
        in block
    )


def test_pipe_exposes_render_adapter_luid():
    text = cpp()

    start = text.index(
        'L"GETFRAMEHANDOFF"'
    )

    end = text.index(
        'L"GETSETTINGS"',
        start,
    )

    block = text[start:end]

    assert (
        'L" RENDER_ADAPTER_LUID_HIGH="'
        in block
    )

    assert (
        'L" RENDER_ADAPTER_LUID_LOW="'
        in block
    )


def test_existing_lifecycle_telemetry_preserved():
    text = cpp()

    for token in (
        'L" ASSIGN_CALLS="',
        'L" UNASSIGN_CALLS="',
        'L" ACTIVE_PROCESSORS="',
        'L" PROCESSORS="',
        'L" PROCESSED="',
        'L" FAILURES="',
        'L" DROPPED="',
    ):
        assert token in text
