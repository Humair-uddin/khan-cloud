#include <Windows.h>

#include <d3d11_1.h>
#include <dxgi1_2.h>
#include <wrl/client.h>

#include <chrono>
#include <cstdint>
#include <iostream>
#include <optional>
#include <sstream>
#include <string>
#include <thread>

using Microsoft::WRL::ComPtr;

namespace
{
    constexpr wchar_t kPipeName[] =
        LR"(\\.\pipe\KhanCloudVirtualDisplay)";

    constexpr wchar_t kDiscoveryCommand[] =
        L"GETFRAMEHANDOFF";

    constexpr DWORD kPipeWaitMs = 2000;
    constexpr DWORD kConsumerAcquireMs = 100;
    constexpr DWORD kRetryDelayMs = 16;

    struct HandoffMetadata
    {
        bool Available = false;
        std::wstring Name;
        UINT64 Generation = 0;
        UINT Width = 0;
        UINT Height = 0;
        DXGI_FORMAT Format = DXGI_FORMAT_UNKNOWN;
        UINT64 ProducerKey = 0;
        UINT64 ConsumerKey = 1;
    };

    std::wstring GetToken(
        const std::wstring& text,
        const std::wstring& key)
    {
        const std::wstring prefix = key + L"=";
        const size_t start = text.find(prefix);

        if (start == std::wstring::npos)
        {
            return {};
        }

        size_t valueStart = start + prefix.size();

        if (
            valueStart < text.size() &&
            text[valueStart] == L'"'
        )
        {
            ++valueStart;

            const size_t end =
                text.find(L'"', valueStart);

            if (end == std::wstring::npos)
            {
                return {};
            }

            return text.substr(
                valueStart,
                end - valueStart
            );
        }

        size_t end = text.find(L' ', valueStart);

        if (end == std::wstring::npos)
        {
            end = text.size();
        }

        return text.substr(
            valueStart,
            end - valueStart
        );
    }

    bool ParseUnsigned64(
        const std::wstring& text,
        UINT64& value)
    {
        try
        {
            size_t consumed = 0;

            value = std::stoull(
                text,
                &consumed,
                10
            );

            return consumed == text.size();
        }
        catch (...)
        {
            return false;
        }
    }

    bool ParseUnsigned32(
        const std::wstring& text,
        UINT& value)
    {
        UINT64 parsed = 0;

        if (!ParseUnsigned64(text, parsed))
        {
            return false;
        }

        if (parsed > UINT_MAX)
        {
            return false;
        }

        value = static_cast<UINT>(parsed);
        return true;
    }

    std::optional<HandoffMetadata>
    ParseDiscoveryResponse(
        const std::wstring& response)
    {
        HandoffMetadata metadata;

        if (
            response.find(
                L"FRAMEHANDOFF AVAILABLE=false"
            ) == 0
        )
        {
            return metadata;
        }

        if (
            response.find(
                L"FRAMEHANDOFF AVAILABLE=true"
            ) != 0
        )
        {
            return std::nullopt;
        }

        metadata.Available = true;
        metadata.Name =
            GetToken(response, L"NAME");

        UINT format = 0;

        if (
            metadata.Name.empty() ||
            !ParseUnsigned64(
                GetToken(response, L"GENERATION"),
                metadata.Generation
            ) ||
            !ParseUnsigned32(
                GetToken(response, L"WIDTH"),
                metadata.Width
            ) ||
            !ParseUnsigned32(
                GetToken(response, L"HEIGHT"),
                metadata.Height
            ) ||
            !ParseUnsigned32(
                GetToken(response, L"FORMAT"),
                format
            ) ||
            !ParseUnsigned64(
                GetToken(response, L"PRODUCER_KEY"),
                metadata.ProducerKey
            ) ||
            !ParseUnsigned64(
                GetToken(response, L"CONSUMER_KEY"),
                metadata.ConsumerKey
            )
        )
        {
            return std::nullopt;
        }

        metadata.Format =
            static_cast<DXGI_FORMAT>(format);

        if (
            metadata.Width == 0 ||
            metadata.Height == 0 ||
            metadata.Format == DXGI_FORMAT_UNKNOWN
        )
        {
            return std::nullopt;
        }

        return metadata;
    }

    bool QueryDiscovery(
        HandoffMetadata& metadata)
    {
        if (
            !WaitNamedPipeW(
                kPipeName,
                kPipeWaitMs
            )
        )
        {
            return false;
        }

        HANDLE pipe = CreateFileW(
            kPipeName,
            GENERIC_READ | GENERIC_WRITE,
            0,
            nullptr,
            OPEN_EXISTING,
            0,
            nullptr
        );

        if (pipe == INVALID_HANDLE_VALUE)
        {
            return false;
        }

        const DWORD commandBytes =
            static_cast<DWORD>(
                wcslen(kDiscoveryCommand) *
                sizeof(wchar_t)
            );

        DWORD bytesWritten = 0;

        const BOOL writeOk = WriteFile(
            pipe,
            kDiscoveryCommand,
            commandBytes,
            &bytesWritten,
            nullptr
        );

        if (
            !writeOk ||
            bytesWritten != commandBytes
        )
        {
            CloseHandle(pipe);
            return false;
        }

        wchar_t responseBuffer[1024] = {};
        DWORD bytesRead = 0;

        const BOOL readOk = ReadFile(
            pipe,
            responseBuffer,
            sizeof(responseBuffer) -
                sizeof(wchar_t),
            &bytesRead,
            nullptr
        );

        CloseHandle(pipe);

        if (
            !readOk ||
            bytesRead == 0 ||
            bytesRead % sizeof(wchar_t) != 0
        )
        {
            return false;
        }

        responseBuffer[
            bytesRead / sizeof(wchar_t)
        ] = L'\0';

        auto parsed =
            ParseDiscoveryResponse(
                responseBuffer
            );

        if (!parsed.has_value())
        {
            return false;
        }

        metadata = *parsed;
        return true;
    }

    HRESULT CreateConsumerDevice(
        ComPtr<ID3D11Device1>& device,
        ComPtr<ID3D11DeviceContext>& context)
    {
        UINT flags = D3D11_CREATE_DEVICE_BGRA_SUPPORT;

#ifdef _DEBUG
        flags |= D3D11_CREATE_DEVICE_DEBUG;
#endif

        const D3D_FEATURE_LEVEL levels[] =
        {
            D3D_FEATURE_LEVEL_11_1,
            D3D_FEATURE_LEVEL_11_0,
        };

        ComPtr<ID3D11Device> baseDevice;
        D3D_FEATURE_LEVEL selectedLevel = {};

        HRESULT hr = D3D11CreateDevice(
            nullptr,
            D3D_DRIVER_TYPE_HARDWARE,
            nullptr,
            flags,
            levels,
            ARRAYSIZE(levels),
            D3D11_SDK_VERSION,
            &baseDevice,
            &selectedLevel,
            &context
        );

        if (hr == E_INVALIDARG)
        {
            hr = D3D11CreateDevice(
                nullptr,
                D3D_DRIVER_TYPE_HARDWARE,
                nullptr,
                flags,
                &levels[1],
                1,
                D3D11_SDK_VERSION,
                &baseDevice,
                &selectedLevel,
                &context
            );
        }

        if (FAILED(hr))
        {
            return hr;
        }

        return baseDevice.As(&device);
    }

    HRESULT OpenSharedFrame(
        ID3D11Device1* device,
        const HandoffMetadata& metadata,
        ComPtr<ID3D11Texture2D>& texture,
        ComPtr<IDXGIKeyedMutex>& mutex)
    {
        texture.Reset();
        mutex.Reset();

        HRESULT hr =
            device->OpenSharedResourceByName(
                metadata.Name.c_str(),
                DXGI_SHARED_RESOURCE_READ |
                    DXGI_SHARED_RESOURCE_WRITE,
                IID_PPV_ARGS(&texture)
            );

        if (FAILED(hr))
        {
            return hr;
        }

        D3D11_TEXTURE2D_DESC desc = {};
        texture->GetDesc(&desc);

        if (
            desc.Width != metadata.Width ||
            desc.Height != metadata.Height ||
            desc.Format != metadata.Format
        )
        {
            texture.Reset();
            return E_INVALIDARG;
        }

        return texture.As(&mutex);
    }

    HRESULT ConsumeOneFrame(
        IDXGIKeyedMutex* mutex,
        const HandoffMetadata& metadata)
    {
        HRESULT hr = mutex->AcquireSync(
            metadata.ConsumerKey,
            kConsumerAcquireMs
        );

        if (
            hr == static_cast<HRESULT>(
                WAIT_TIMEOUT
            )
        )
        {
            return S_FALSE;
        }

        if (
            hr == static_cast<HRESULT>(
                WAIT_ABANDONED
            )
        )
        {
            return E_FAIL;
        }

        if (FAILED(hr))
        {
            return hr;
        }

        //
        // GPU-only validation boundary.
        //
        // The consumer intentionally does not Map(), stage,
        // copy to CPU memory, encode, or perform networking.
        // Successful keyed-mutex acquisition proves that the
        // external process can synchronize with the VDD-owned
        // shared D3D11 frame resource.
        //

        return mutex->ReleaseSync(
            metadata.ProducerKey
        );
    }
}

int wmain(int argc, wchar_t** argv)
{
    UINT targetFrames = 120;

    if (argc >= 2)
    {
        UINT parsed = 0;

        if (
            !ParseUnsigned32(
                argv[1],
                parsed
            ) ||
            parsed == 0
        )
        {
            std::wcerr
                << L"Invalid frame count."
                << std::endl;

            return 2;
        }

        targetFrames = parsed;
    }

    ComPtr<ID3D11Device1> device;
    ComPtr<ID3D11DeviceContext> context;

    HRESULT hr = CreateConsumerDevice(
        device,
        context
    );

    if (FAILED(hr))
    {
        std::wcerr
            << L"D3D11 device creation failed. HRESULT="
            << std::hex
            << hr
            << std::endl;

        return 3;
    }

    UINT consumedFrames = 0;
    UINT timeoutCount = 0;
    UINT discoveryMisses = 0;

    UINT64 activeGeneration = 0;
    std::wstring activeName;

    ComPtr<ID3D11Texture2D> texture;
    ComPtr<IDXGIKeyedMutex> mutex;

    while (consumedFrames < targetFrames)
    {
        HandoffMetadata metadata;

        if (!QueryDiscovery(metadata))
        {
            ++discoveryMisses;

            std::this_thread::sleep_for(
                std::chrono::milliseconds(
                    kRetryDelayMs
                )
            );

            continue;
        }

        if (!metadata.Available)
        {
            ++discoveryMisses;

            texture.Reset();
            mutex.Reset();
            activeName.clear();
            activeGeneration = 0;

            std::this_thread::sleep_for(
                std::chrono::milliseconds(
                    kRetryDelayMs
                )
            );

            continue;
        }

        if (
            !texture ||
            !mutex ||
            metadata.Generation !=
                activeGeneration ||
            metadata.Name != activeName
        )
        {
            texture.Reset();
            mutex.Reset();

            hr = OpenSharedFrame(
                device.Get(),
                metadata,
                texture,
                mutex
            );

            if (FAILED(hr))
            {
                std::this_thread::sleep_for(
                    std::chrono::milliseconds(
                        kRetryDelayMs
                    )
                );

                continue;
            }

            activeGeneration =
                metadata.Generation;

            activeName =
                metadata.Name;

            std::wcout
                << L"FRAMEHANDOFF_OPEN"
                << L" GENERATION="
                << activeGeneration
                << L" WIDTH="
                << metadata.Width
                << L" HEIGHT="
                << metadata.Height
                << L" FORMAT="
                << static_cast<UINT>(
                    metadata.Format
                )
                << std::endl;
        }

        hr = ConsumeOneFrame(
            mutex.Get(),
            metadata
        );

        if (hr == S_FALSE)
        {
            ++timeoutCount;
            continue;
        }

        if (FAILED(hr))
        {
            texture.Reset();
            mutex.Reset();
            activeName.clear();
            activeGeneration = 0;

            continue;
        }

        ++consumedFrames;

        if (
            consumedFrames == 1 ||
            consumedFrames % 60 == 0 ||
            consumedFrames == targetFrames
        )
        {
            std::wcout
                << L"FRAME_CONSUMED="
                << consumedFrames
                << std::endl;
        }
    }

    std::wcout
        << L"CONSUMER_RESULT=PASS"
        << L" FRAMES="
        << consumedFrames
        << L" TIMEOUTS="
        << timeoutCount
        << L" DISCOVERY_MISSES="
        << discoveryMisses
        << L" GENERATION="
        << activeGeneration
        << std::endl;

    return 0;
}
