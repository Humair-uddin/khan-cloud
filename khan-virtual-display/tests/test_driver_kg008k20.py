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


def test_named_resource_uses_guid():
    text = read(CPP)

    assert "CoCreateGuid(&resourceGuid)" in text
    assert "StringFromGUID2(" in text

    assert (
        'L"Global\\\\KhanCloud.VDD.Frame."'
        in text
    )

    assert (
        'L"Local\\\\KhanCloud.VDD.Frame."'
        not in text
    )


def test_create_shared_handle_has_name():
    text = read(CPP)

    start = text.index(
        "CreateSharedHandle("
    )

    block = text[start:start + 600]

    assert "resourceName.c_str()" in block


def test_resource_name_is_saved():
    text = read(CPP)

    assert (
        "m_FrameHandoffResourceName = "
        "resourceName;"
        in text
    )


def test_resource_name_cleared_on_reset():
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
        "m_FrameHandoffResourceName.clear();"
        in unlocked_block
    )

    assert (
        "CloseHandle(m_FrameHandoffSharedHandle)"
        in unlocked_block
    )

    assert (
        "m_FrameHandoffSharedHandle = nullptr;"
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

def test_metadata_does_not_expose_raw_handle():
    text = read(CPP)

    start = text.index(
        "bool SwapChainProcessor::"
        "GetFrameHandoffDiscoveryMetadata("
    )

    end = text.index(
        "void SwapChainProcessor::"
        "ResetFrameHandoff()",
        start,
    )

    block = text[start:end]

    assert (
        "ResourceName = "
        "m_FrameHandoffResourceName;"
        in block
    )

    assert (
        "Generation = "
        "m_FrameHandoffGeneration;"
        in block
    )

    assert (
        "Desc = m_FrameHandoffDesc;"
        in block
    )

    # A validity guard such as
    # m_FrameHandoffSharedHandle == nullptr is expected.
    # The discovery API must simply not return or assign
    # the raw HANDLE as metadata.
    assert "ResourceName = m_FrameHandoffSharedHandle" not in block
    assert "Generation = m_FrameHandoffSharedHandle" not in block
    assert "Desc = m_FrameHandoffSharedHandle" not in block
    assert "SharedHandle = m_FrameHandoffSharedHandle" not in block


def test_context_discovery_declaration_exists():
    text = read(HDR)

    assert (
        text.count(
            "bool "
            "GetFrameHandoffDiscoveryMetadata("
        )
        == 2
    )


def test_context_discovery_is_locked():
    text = read(CPP)

    start = text.index(
        "bool IndirectDeviceContext::"
        "GetFrameHandoffDiscoveryMetadata("
    )

    end = text.index(
        "void IndirectDeviceContext::",
        start,
    )

    block = text[start:end]

    assert (
        "std::lock_guard<std::mutex>"
        in block
    )

    assert (
        "m_ProcessingThreadsMutex"
        in block
    )


def test_context_requires_one_processor():
    text = read(CPP)

    start = text.index(
        "bool IndirectDeviceContext::"
        "GetFrameHandoffDiscoveryMetadata("
    )

    end = text.index(
        "void IndirectDeviceContext::",
        start,
    )

    block = text[start:end]

    assert (
        "m_ProcessingThreads.size() != 1"
        in block
    )


def test_nonblocking_k19_contract_preserved():
    text = read(CPP)

    assert "AcquireSync(" in text
    assert "WAIT_TIMEOUT" in text
    assert "return S_FALSE;" in text
    assert "ReleaseSync(1)" in text


def test_no_cpu_pixel_transport():
    text = read(CPP)

    start = text.index(
        "HRESULT SwapChainProcessor::"
        "ProcessFrame("
    )

    end = text.index(
        "void SwapChainProcessor::RunCore()",
        start,
    )

    block = text[start:end].lower()

    assert "->map(" not in block
    assert "->unmap(" not in block



def test_current_pipe_acl_is_hardened():
    text = read(CPP)

    assert 'L"D:(A;;GA;;;WD)"' not in text

    assert (
        'L"D:P'
        '(A;;GA;;;SY)'
        '(A;;GA;;;BA)"'
        in text
    )

def test_k20_pipe_has_frame_handoff_command():
    text = read(CPP)

    assert 'L"GETFRAMEHANDOFF"' in text
    assert 'L"FRAMEHANDOFF AVAILABLE=false"' in text
    assert 'L"FRAMEHANDOFF AVAILABLE=true"' in text


def test_k20_pipe_publishes_gpu_metadata_not_handle():
    text = read(CPP)

    start = text.index(
        'L"GETFRAMEHANDOFF"'
    )

    end = text.index(
        'L"GETSETTINGS"',
        start,
    )

    block = text[start:end]

    for token in (
        'L" GENERATION="',
        'L" WIDTH="',
        'L" HEIGHT="',
        'L" FORMAT="',
        'L" PRODUCER_KEY=0"',
        'L" CONSUMER_KEY=1"',
    ):
        assert token in block

    assert "m_FrameHandoffSharedHandle" not in block


def test_k20_pipe_context_pointer_is_fully_qualified():
    text = read(CPP)

    assert (
        "Microsoft::IndirectDisp::"
        "IndirectDeviceContext* "
        "g_KhanActiveDeviceContext"
        in text
    )


def test_k20_pipe_context_lifetime_is_guarded():
    text = read(CPP)

    assert "g_KhanActiveDeviceContextMutex" in text
    assert "g_KhanActiveDeviceContext = this;" in text
    assert "g_KhanActiveDeviceContext == this" in text
    assert "g_KhanActiveDeviceContext = nullptr;" in text


def test_k20_pipe_command_uses_context_mutex():
    text = read(CPP)

    start = text.index(
        'L"GETFRAMEHANDOFF"'
    )

    end = text.index(
        'L"GETSETTINGS"',
        start,
    )

    block = text[start:end]

    assert (
        "g_KhanActiveDeviceContextMutex"
        in block
    )

    assert (
        "GetFrameHandoffDiscoveryMetadata("
        in block
    )


def test_k20_pipe_acl_is_not_world_accessible():
    text = read(CPP)

    assert 'L"D:(A;;GA;;;WD)"' not in text

    assert (
        'L"D:P'
        '(A;;GA;;;SY)'
        '(A;;GA;;;BA)"'
        in text
    )
def test_k20_frame_handoff_response_delivery_is_checked():
    text = read(CPP)

    start = text.index(
        'L"GETFRAMEHANDOFF"'
    )

    end = text.index(
        'L"GETSETTINGS"',
        start,
    )

    block = text[start:end]

    assert "BOOL writeResult" in block
    assert "WriteFile(" in block
    assert "!writeResult" in block
    assert "bytesWritten != bytesToWrite" in block
    assert "FlushFileBuffers(hPipe)" in block

    assert (
        "GETFRAMEHANDOFF response write failed."
        in block
    )

    assert (
        "GETFRAMEHANDOFF response flush failed."
        in block
    )
