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


def process_frame_block():
    text = read(CPP)

    start = text.index(
        "HRESULT SwapChainProcessor::ProcessFrame("
    )

    end = text.index(
        "void SwapChainProcessor::RunCore()",
        start,
    )

    return text[start:end]


def test_k17_frame_processor_declared():
    text = read(HDR)

    assert "HRESULT ProcessFrame(" in text
    assert "IDXGIResource* FrameResource" in text


def test_k17_frame_counters_are_per_processor():
    text = read(HDR)

    assert (
        "std::atomic<UINT64> "
        "m_ProcessedFrameCount{0};"
        in text
    )

    assert (
        "std::atomic<UINT64> "
        "m_FrameProcessingFailureCount{0};"
        in text
    )

def test_k17_resolves_real_iddcx_resource_to_d3d11_texture():
    block = process_frame_block()

    assert "IDXGIResource* FrameResource" in block
    assert "ComPtr<ID3D11Texture2D> frameTexture;" in block
    assert "FrameResource->QueryInterface(" in block
    assert "IID_PPV_ARGS(&frameTexture)" in block


def test_k17_validates_texture_description():
    block = process_frame_block()

    assert "D3D11_TEXTURE2D_DESC frameDesc = {};" in block
    assert "frameTexture->GetDesc(&frameDesc);" in block

    for token in (
        "frameDesc.Width == 0",
        "frameDesc.Height == 0",
        "frameDesc.ArraySize == 0",
        "frameDesc.MipLevels == 0",
    ):
        assert token in block


def test_k17_processing_occurs_before_iddcx_frame_release():
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


def test_k17_processing_failure_does_not_abandon_windows_frame():
    text = read(CPP)

    start = text.index(
        "HRESULT frameProcessingHr"
    )

    reset = text.index(
        "AcquiredBuffer.Reset();",
        start,
    )

    block = text[start:reset]

    assert "FAILED(frameProcessingHr)" in block
    assert "break;" not in block
    assert "return;" not in block


def test_k17_does_not_cpu_map_acquired_frame():
    block = process_frame_block()

    assert "DeviceContext->Map(" not in block
    assert "DeviceContext->Unmap(" not in block


def test_k17_does_not_embed_encoder_or_network_transport():
    block = process_frame_block().lower()

    for forbidden in (
        "nvenc",
        "sunshine",
        "webrtc",
        "socket(",
        "send(",
    ):
        assert forbidden not in block


def test_k17_preserves_existing_iddcx_completion_contract():
    text = read(CPP)

    assert (
        "IddCxSwapChainReleaseAndAcquireBuffer2"
        in text
    )

    assert (
        "IddCxSwapChainFinishedProcessingFrame"
        in text
    )

    assert "m_hTerminateEvent" in text
    assert "WaitForMultipleObjects" in text
