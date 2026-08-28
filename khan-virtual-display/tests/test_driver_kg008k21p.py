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


def source():
    return CPP.read_text()


def header():
    return HDR.read_text()


def test_atomic_runtime_counters():
    h = header()

    assert "#include <atomic>" in h

    assert (
        "std::atomic<UINT64> "
        "m_ProcessedFrameCount{0};"
        in h
    )

    assert (
        "std::atomic<UINT64> "
        "m_FrameProcessingFailureCount{0};"
        in h
    )

    assert (
        "std::atomic<UINT64> "
        "m_FrameHandoffDroppedCount{0};"
        in h
    )


def test_handoff_state_mutex():
    h = header()

    assert (
        "mutable std::mutex "
        "m_FrameHandoffStateMutex;"
        in h
    )

    assert (
        "void ResetFrameHandoffUnlocked();"
        in h
    )


def test_discovery_atomic_snapshot():
    s = source()

    start = s.index(
        "bool SwapChainProcessor::"
        "GetFrameHandoffDiscoveryMetadata("
    )

    end = s.index(
        "void SwapChainProcessor::"
        "ResetFrameHandoffUnlocked()",
        start,
    )

    block = s[start:end]

    assert "m_ProcessedFrameCount.load(" in block
    assert (
        "m_FrameProcessingFailureCount.load("
        in block
    )
    assert (
        "m_FrameHandoffDroppedCount.load("
        in block
    )

    assert (
        "std::memory_order_relaxed"
        in block
    )

    assert (
        "m_FrameHandoffStateMutex"
        in block
    )


def test_reset_lock_split():
    s = source()

    assert (
        "void SwapChainProcessor::"
        "ResetFrameHandoffUnlocked()"
        in s
    )

    start = s.index(
        "void SwapChainProcessor::"
        "ResetFrameHandoff()"
    )

    end = s.index(
        "HRESULT SwapChainProcessor::"
        "EnsureFrameHandoffTexture(",
        start,
    )

    block = s[start:end]

    assert (
        "m_FrameHandoffStateMutex"
        in block
    )

    assert (
        "ResetFrameHandoffUnlocked();"
        in block
    )


def test_ensure_does_not_self_deadlock():
    s = source()

    start = s.index(
        "HRESULT SwapChainProcessor::"
        "EnsureFrameHandoffTexture("
    )

    end = s.index(
        "HRESULT SwapChainProcessor::"
        "ProcessFrame(",
        start,
    )

    block = s[start:end]

    assert (
        "m_FrameHandoffStateMutex"
        in block
    )

    assert (
        "ResetFrameHandoffUnlocked();"
        in block
    )

    assert "ResetFrameHandoff();" not in block


def test_processframe_uses_local_com_snapshot():
    s = source()

    start = s.index(
        "HRESULT SwapChainProcessor::"
        "ProcessFrame("
    )

    end = s.index(
        "void SwapChainProcessor::RunCore()",
        start,
    )

    block = s[start:end]

    assert (
        "ComPtr<ID3D11Texture2D> "
        "handoffTexture;"
        in block
    )

    assert (
        "ComPtr<IDXGIKeyedMutex> "
        "handoffMutex;"
        in block
    )

    assert (
        "handoffMutex->AcquireSync("
        in block
    )

    assert (
        "handoffMutex->ReleaseSync(1)"
        in block
    )

    assert (
        "handoffTexture.Get()"
        in block
    )


def test_device_snapshot_reports_processor_count():
    s = source()

    start = s.index(
        "bool IndirectDeviceContext::"
        "GetFrameHandoffDiscoveryMetadata("
    )

    end = s.index(
        "void IndirectDeviceContext::"
        "UnassignSwapChain(",
        start,
    )

    block = s[start:end]

    assert "ProcessorCount" in block

    assert (
        "m_ProcessingThreads.size()"
        in block
    )

    assert "ProcessedFrames = 0;" in block
    assert "ProcessingFailures = 0;" in block
    assert "DroppedFrames = 0;" in block


def test_pipe_reports_runtime_truth():
    s = source()

    start = s.index(
        'L"GETFRAMEHANDOFF"'
    )

    end = s.index(
        'L"GETSETTINGS"',
        start,
    )

    block = s[start:end]

    for token in (
        'L" PROCESSORS="',
        'L" PROCESSED="',
        'L" FAILURES="',
        'L" DROPPED="',
        'L" DIAG_GENERATION="',
    ):
        assert token in block


def test_available_true_generation_not_duplicated():
    s = source()

    start = s.index(
        'L"GETFRAMEHANDOFF"'
    )

    end = s.index(
        'L"GETSETTINGS"',
        start,
    )

    block = s[start:end]

    # Production identity generation remains GENERATION.
    assert 'L" GENERATION="' in block

    # Telemetry generation has a separate key.
    assert 'L" DIAG_GENERATION="' in block


def test_no_cpu_readback_added():
    s = source()

    start = s.index(
        "HRESULT SwapChainProcessor::"
        "ProcessFrame("
    )

    end = s.index(
        "void SwapChainProcessor::RunCore()",
        start,
    )

    block = s[start:end]

    assert "D3D11_USAGE_STAGING" not in block
    assert "D3D11_CPU_ACCESS_READ" not in block
    assert "Map(" not in block
