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


def read(path):
    return path.read_text()


def ensure_block():
    text = read(CPP)

    start = text.index(
        "HRESULT SwapChainProcessor::EnsureFrameHandoffTexture("
    )

    end = text.index(
        "HRESULT SwapChainProcessor::ProcessFrame(",
        start,
    )

    return text[start:end]


def process_block():
    text = read(CPP)

    start = text.index(
        "HRESULT SwapChainProcessor::ProcessFrame("
    )

    end = text.index(
        "void SwapChainProcessor::RunCore()",
        start,
    )

    return text[start:end]


def test_k19_uses_nt_shared_handle_texture():
    block = ensure_block()

    assert "D3D11_RESOURCE_MISC_SHARED_NTHANDLE" in block
    assert "D3D11_RESOURCE_MISC_SHARED_KEYEDMUTEX" in block


def test_k19_creates_real_nt_shared_handle():
    block = ensure_block()

    assert "IDXGIResource1" in block
    assert "CreateSharedHandle(" in block
    assert "m_FrameHandoffSharedHandle" in read(HDR)


def test_k19_has_keyed_mutex():
    text = read(HDR)
    block = ensure_block()

    assert "ComPtr<IDXGIKeyedMutex>" in text
    assert "newTexture.As(&newMutex)" in block


def test_k19_producer_acquire_is_nonblocking():
    block = process_block()

    assert "AcquireSync(" in block

    acquire = block.index("AcquireSync(")
    tail = block[acquire:acquire + 160]

    assert "0" in tail


def test_k19_drops_frame_on_busy_consumer():
    block = process_block()

    assert "WAIT_TIMEOUT" in block
    assert "m_FrameHandoffDroppedCount" in block
    assert "return S_FALSE;" in block


def test_k19_key_handoff_protocol():
    block = process_block()

    assert "AcquireSync(" in block
    assert "ReleaseSync(1)" in block


def test_k19_abandoned_mutex_resets_shared_resource():
    block = process_block()

    assert "WAIT_ABANDONED" in block
    assert "ResetFrameHandoff();" in block


def test_k19_closes_nt_handle_on_reset():
    text = read(CPP)

    unlocked_start = text.index(
        "void SwapChainProcessor::"
        "ResetFrameHandoffUnlocked()"
    )

    locked_start = text.index(
        "void SwapChainProcessor::"
        "ResetFrameHandoff()",
        unlocked_start,
    )

    ensure_start = text.index(
        "HRESULT SwapChainProcessor::"
        "EnsureFrameHandoffTexture(",
        locked_start,
    )

    unlocked_block = text[
        unlocked_start:locked_start
    ]

    locked_block = text[
        locked_start:ensure_start
    ]

    assert (
        "CloseHandle(m_FrameHandoffSharedHandle)"
        in unlocked_block
    )

    assert (
        "m_FrameHandoffSharedHandle = nullptr;"
        in unlocked_block
    )

    assert (
        "m_FrameHandoffResourceName.clear();"
        in unlocked_block
    )

    assert (
        "ResetFrameHandoffUnlocked();"
        in locked_block
    )

    assert (
        "m_FrameHandoffStateMutex"
        in locked_block
    )

def test_k19_preserves_gpu_only_path():
    block = process_block().lower()

    assert "copyresource(" in block

    for forbidden in (
        "->map(",
        "->unmap(",
        "nvenc",
        "sunshine",
        "webrtc",
        "socket(",
        "send(",
    ):
        assert forbidden not in block


def test_k19_windows_completion_still_follows_processing():
    text = read(CPP)

    process = text.index(
        "ProcessFrame(AcquiredBuffer.Get())"
    )

    reset = text.index(
        "AcquiredBuffer.Reset();",
        process,
    )

    finished = text.index(
        "IddCxSwapChainFinishedProcessingFrame",
        reset,
    )

    assert process < reset < finished
