from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

CONSUMER = (
    ROOT
    / "consumer"
    / "KhanFrameConsumer"
    / "KhanFrameConsumer.cpp"
)

PROJECT = (
    ROOT
    / "consumer"
    / "KhanFrameConsumer"
    / "KhanFrameConsumer.vcxproj"
)

DRIVER = (
    ROOT
    / "driver"
    / "KhanVirtualDisplay"
    / "Driver.cpp"
)


def read(path):
    return path.read_text()


def test_consumer_files_exist():
    assert CONSUMER.is_file()
    assert PROJECT.is_file()


def test_consumer_uses_existing_khan_pipe():
    text = read(CONSUMER)

    assert (
        r"\\.\pipe\KhanCloudVirtualDisplay"
        in text
    )

    assert "GETFRAMEHANDOFF" in text


def test_consumer_parses_discovery_contract():
    text = read(CONSUMER)

    for token in (
        "AVAILABLE=true",
        'GetToken(response, L"NAME")',
        'GetToken(response, L"GENERATION")',
        'GetToken(response, L"WIDTH")',
        'GetToken(response, L"HEIGHT")',
        'GetToken(response, L"FORMAT")',
        'GetToken(response, L"PRODUCER_KEY")',
        'GetToken(response, L"CONSUMER_KEY")',
    ):
        assert token in text


def test_consumer_opens_named_gpu_resource():
    text = read(CONSUMER)

    assert "ID3D11Device1" in text
    assert "OpenSharedResourceByName(" in text
    assert "ID3D11Texture2D" in text


def test_consumer_uses_keyed_mutex():
    text = read(CONSUMER)

    assert "IDXGIKeyedMutex" in text
    assert "AcquireSync(" in text
    assert "ReleaseSync(" in text


def test_consumer_uses_protocol_keys_not_hardcoded_sync_keys():
    text = read(CONSUMER)

    assert "metadata.ConsumerKey" in text
    assert "metadata.ProducerKey" in text

    assert (
        "mutex->AcquireSync(\n"
        "            metadata.ConsumerKey,"
        in text
    )

    assert (
        "mutex->ReleaseSync(\n"
        "            metadata.ProducerKey"
        in text
    )


def test_consumer_validates_texture_metadata():
    text = read(CONSUMER)

    assert "desc.Width != metadata.Width" in text
    assert "desc.Height != metadata.Height" in text
    assert "desc.Format != metadata.Format" in text


def test_consumer_handles_generation_change():
    text = read(CONSUMER)

    assert (
        "metadata.Generation !="
        in text
    )

    assert "activeGeneration" in text
    assert "activeName" in text


def test_consumer_does_not_cpu_readback():
    text = read(CONSUMER)

    forbidden = (
        "D3D11_USAGE_STAGING",
        "D3D11_CPU_ACCESS_READ",
        "DeviceContext->Map(",
        "context->Map(",
        ".Map(",
        "GetData(",
    )

    for token in forbidden:
        assert token not in text


def test_consumer_does_not_encode_or_network_frames():
    text = read(CONSUMER)

    forbidden = (
        "NVENC",
        "NvEnc",
        "libavcodec",
        "send(",
        "WSASend",
        "socket(",
    )

    for token in forbidden:
        assert token not in text


def test_project_is_native_x64_console_application():
    text = read(PROJECT)

    assert "<ConfigurationType>Application</ConfigurationType>" in text
    assert "<PlatformToolset>v143</PlatformToolset>" in text
    assert "<SubSystem>Console</SubSystem>" in text
    assert "<LanguageStandard>stdcpp17</LanguageStandard>" in text
    assert "d3d11.lib" in text
    assert "dxgi.lib" in text


def test_driver_producer_contract_matches_consumer():
    text = read(DRIVER)

    assert 'L"GETFRAMEHANDOFF"' in text
    assert 'L" PRODUCER_KEY=0"' in text
    assert 'L" CONSUMER_KEY=1"' in text

    # K21P uses a local COM snapshot so member reset
    # cannot invalidate the resource during GPU work.
    assert (
        "handoffMutex->AcquireSync(\n"
        "                0,\n"
        "                0"
        in text
    )

    assert (
        "handoffMutex->ReleaseSync(1)"
        in text
    )

def test_driver_remains_nonblocking():
    text = read(DRIVER)

    assert (
        "handoffMutex->AcquireSync(\n"
        "                0,\n"
        "                0"
        in text
    )

    assert "m_FrameHandoffDroppedCount" in text

def test_consumer_is_external_not_driver_embedded():
    consumer_text = read(CONSUMER)
    project_text = read(PROJECT)

    assert "wmain(" in consumer_text
    assert "ConfigurationType>Application" in project_text


def test_consumer_has_no_driver_install_or_restart_logic():
    text = read(CONSUMER)

    forbidden = (
        "pnputil",
        "devcon",
        "Restart-Service",
        "RELOAD_DRIVER",
    )

    for token in forbidden:
        assert token not in text
