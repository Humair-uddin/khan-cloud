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


def test_assign_counter_is_atomic():
    text = hdr()

    assert (
        "std::atomic<UINT64> "
        "m_AssignSwapChainCallCount{0};"
        in text
    )


def test_unassign_counter_is_atomic():
    text = hdr()

    assert (
        "std::atomic<UINT64> "
        "m_UnassignSwapChainCallCount{0};"
        in text
    )


def test_assign_callback_increments():
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

    assert (
        "++m_AssignSwapChainCallCount;"
        in block
    )


def test_unassign_callback_increments():
    text = cpp()

    start = text.index(
        "void IndirectDeviceContext::"
        "UnassignSwapChain("
    )

    end = text.index(
        "void IndirectDeviceContext::"
        "GetSwapChainLifecycleTelemetry(",
        start,
    )

    block = text[start:end]

    assert (
        "++m_UnassignSwapChainCallCount;"
        in block
    )


def test_lifecycle_snapshot_exists():
    text = cpp()

    start = text.index(
        "void IndirectDeviceContext::"
        "GetSwapChainLifecycleTelemetry("
    )

    block = text[
        start:start + 1800
    ]

    assert (
        "m_AssignSwapChainCallCount.load("
        in block
    )

    assert (
        "m_UnassignSwapChainCallCount.load("
        in block
    )

    assert (
        "m_ProcessingThreadsMutex"
        in block
    )

    assert (
        "m_ProcessingThreads.size()"
        in block
    )


def test_lifecycle_snapshot_declared():
    text = hdr()

    assert (
        "GetSwapChainLifecycleTelemetry("
        in text
    )


def test_pipe_calls_lifecycle_snapshot():
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
        "GetSwapChainLifecycleTelemetry("
        in block
    )


def test_pipe_reports_assign_calls():
    text = cpp()

    assert 'L" ASSIGN_CALLS="' in text


def test_pipe_reports_unassign_calls():
    text = cpp()

    assert 'L" UNASSIGN_CALLS="' in text


def test_pipe_reports_active_processors():
    text = cpp()

    assert (
        'L" ACTIVE_PROCESSORS="'
        in text
    )


def test_k21p_telemetry_preserved():
    text = cpp()

    for token in (
        'L" PROCESSORS="',
        'L" PROCESSED="',
        'L" FAILURES="',
        'L" DROPPED="',
        'L" DIAG_GENERATION="',
    ):
        assert token in text


def test_no_cpu_readback_added():
    text = cpp()

    start = text.index(
        "HRESULT SwapChainProcessor::"
        "ProcessFrame("
    )

    end = text.index(
        "void SwapChainProcessor::RunCore()",
        start,
    )

    block = text[start:end]

    assert "D3D11_USAGE_STAGING" not in block
    assert "D3D11_CPU_ACCESS_READ" not in block
    assert "Map(" not in block
