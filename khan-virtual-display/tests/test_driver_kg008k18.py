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


def test_k18_handoff_texture_members_exist():
    text = read(HDR)

    assert "m_FrameHandoffTexture" in text
    assert "m_FrameHandoffDesc" in text
    assert "EnsureFrameHandoffTexture" in text


def test_k18_reuses_matching_gpu_texture():
    block = ensure_block()

    assert "existingTextureMatches" in block
    assert "m_FrameHandoffTexture" in block
    assert "m_FrameHandoffDesc.Width == SourceDesc.Width" in block
    assert "m_FrameHandoffDesc.Height == SourceDesc.Height" in block
    assert "m_FrameHandoffDesc.Format == SourceDesc.Format" in block


def test_k18_gpu_texture_has_no_cpu_access():
    block = ensure_block()

    assert "handoffDesc.Usage = D3D11_USAGE_DEFAULT;" in block
    assert "handoffDesc.CPUAccessFlags = 0;" in block


def test_k18_creates_d3d11_gpu_texture():
    block = ensure_block()

    assert "CreateTexture2D(" in block
    assert "ComPtr<ID3D11Texture2D> newTexture;" in block


def test_k18_processframe_copies_gpu_resource():
    block = process_block()

    assert "EnsureFrameHandoffTexture(" in block
    assert "DeviceContext->CopyResource(" in block

    # K21P intentionally snapshots the shared COM object
    # under the handoff-state mutex before GPU work.
    assert (
        "ComPtr<ID3D11Texture2D> "
        "handoffTexture;"
        in block
    )

    assert "handoffTexture.Get()" in block

def test_k18_does_not_cpu_map_frame():
    block = process_block().lower()

    assert "->map(" not in block
    assert "->unmap(" not in block


def test_k18_does_not_embed_streamer_or_encoder():
    block = process_block().lower()

    for forbidden in (
        "nvenc",
        "sunshine",
        "webrtc",
        "socket(",
        "send(",
    ):
        assert forbidden not in block


def test_k18_preserves_iddcx_release_order():
    text = read(CPP)

    copy = text.index(
        "DeviceContext->CopyResource("
    )

    reset = text.index(
        "AcquiredBuffer.Reset();",
        copy,
    )

    finished = text.index(
        "IddCxSwapChainFinishedProcessingFrame",
        reset,
    )

    assert copy < reset < finished


def test_k18_no_windows_frame_abandon_on_copy_failure():
    text = read(CPP)

    call = text.index(
        "HRESULT frameProcessingHr"
    )

    reset = text.index(
        "AcquiredBuffer.Reset();",
        call,
    )

    block = text[call:reset]

    assert "FAILED(frameProcessingHr)" in block
    assert "break;" not in block
    assert "return;" not in block
