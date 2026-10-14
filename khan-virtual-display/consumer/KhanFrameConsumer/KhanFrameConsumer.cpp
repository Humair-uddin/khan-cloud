#include <Windows.h>

#include <d3d11_1.h>
#include <dxgi1_2.h>
#include <dxgi1_4.h> // RAW-N8G38Q22C
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

        // RAW-N8G38Q21B4:
        // These values are already emitted by GETFRAMEHANDOFF.
        LONG RenderAdapterLuidHigh = 0;
        ULONG RenderAdapterLuidLow = 0;
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

        // RAW-N8G38Q15B:
        //
        // The current VDD discovery response emits NAME=\"...\".
        // Accept that wire representation as well as a normal quoted value.
        if (
            valueStart + 1 < text.size() &&
            text[valueStart] == L'\\' &&
            text[valueStart + 1] == L'"'
        )
        {
            valueStart += 2;

            const size_t end =
                text.find(
                    L"\\\"",
                    valueStart
                );

            if (end == std::wstring::npos)
            {
                return {};
            }

            return text.substr(
                valueStart,
                end - valueStart
            );
        }

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

        const std::wstring renderLuidHighText =
            GetToken(
                response,
                L"RENDER_ADAPTER_LUID_HIGH"
            );

        const std::wstring renderLuidLowText =
            GetToken(
                response,
                L"RENDER_ADAPTER_LUID_LOW"
            );

        if (!renderLuidHighText.empty())
        {
            try
            {
                size_t consumed = 0;

                const long long parsedHigh =
                    std::stoll(
                        renderLuidHighText,
                        &consumed,
                        10
                    );

                if (
                    consumed ==
                    renderLuidHighText.size() &&
                    parsedHigh >= LONG_MIN &&
                    parsedHigh <= LONG_MAX
                )
                {
                    metadata.RenderAdapterLuidHigh =
                        static_cast<LONG>(
                            parsedHigh
                        );
                }
            }
            catch (...)
            {
                // Diagnostic field only.
            }
        }

        if (!renderLuidLowText.empty())
        {
            UINT64 parsedLow = 0;

            if (
                ParseUnsigned64(
                    renderLuidLowText,
                    parsedLow
                ) &&
                parsedLow <= ULONG_MAX
            )
            {
                metadata.RenderAdapterLuidLow =
                    static_cast<ULONG>(
                        parsedLow
                    );
            }
        }

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
        // RAW-N8G38Q15A:
        //
        // The Khan VDD control pipe also carries optional diagnostic/log
        // messages. GETFRAMEHANDOFF therefore cannot assume that the first
        // message returned after the request is the UTF-16 FRAMEHANDOFF
        // response.
        //
        // Read complete message-mode records and ignore unrelated records
        // until the authoritative FRAMEHANDOFF response arrives.
        constexpr DWORD kMaxDiscoveryMessages = 64;

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

        // RAW-N8G38Q18A:
        //
        // The server creates a message-type named pipe. Explicitly switch
        // this client handle to message-read mode so diagnostic log records
        // and the UTF-16 FRAMEHANDOFF response remain separate messages.
        DWORD readMode = PIPE_READMODE_MESSAGE;

        if (
            !SetNamedPipeHandleState(
                pipe,
                &readMode,
                nullptr,
                nullptr
            )
        )
        {
            CloseHandle(pipe);
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

        bool discovered = false;

        for (
            DWORD messageIndex = 0;
            messageIndex < kMaxDiscoveryMessages;
            ++messageIndex
        )
        {
            BYTE rawBuffer[4096] = {};
            DWORD bytesRead = 0;

            const BOOL readOk = ReadFile(
                pipe,
                rawBuffer,
                sizeof(rawBuffer) -
                    sizeof(wchar_t),
                &bytesRead,
                nullptr
            );

            // RAW-N8G38Q19B:
            // Bounded consumer-side evidence of exactly what the named pipe
            // returned before any UTF-16 assumptions or discovery parsing.
            static LONG diagnosticReadCount = 0;

            const LONG diagnosticIndex =
                InterlockedIncrement(
                    &diagnosticReadCount
                );

            if (diagnosticIndex <= 32)
            {
                const DWORD readError =
                    readOk
                        ? ERROR_SUCCESS
                        : GetLastError();

                std::wcerr
                    << L"Q19B_PIPE_READ"
                    << L" INDEX="
                    << diagnosticIndex
                    << L" MESSAGE_INDEX="
                    << messageIndex
                    << L" OK="
                    << (readOk ? 1 : 0)
                    << L" ERROR="
                    << readError
                    << L" BYTES="
                    << bytesRead
                    << L" HEX=";

                const DWORD previewBytes =
                    (bytesRead < 32)
                        ? bytesRead
                        : 32;

                static constexpr wchar_t kHex[] =
                    L"0123456789ABCDEF";

                for (
                    DWORD i = 0;
                    i < previewBytes;
                    ++i
                )
                {
                    const BYTE b = rawBuffer[i];

                    std::wcerr
                        << kHex[(b >> 4) & 0x0F]
                        << kHex[b & 0x0F];
                }

                std::wcerr
                    << std::endl;
            }

            if (!readOk)
            {
                const DWORD error = GetLastError();

                if (error == ERROR_MORE_DATA)
                {
                    // No expected discovery record approaches this buffer
                    // size. Treat an oversized unrelated message as a miss
                    // rather than parsing a truncated response.
                    continue;
                }

                break;
            }

            if (
                bytesRead == 0 ||
                bytesRead % sizeof(wchar_t) != 0
            )
            {
                // Pipe logging is narrow-byte traffic. Ignore it.
                continue;
            }

            const size_t wcharCount =
                bytesRead / sizeof(wchar_t);

            auto* wide =
                reinterpret_cast<wchar_t*>(rawBuffer);

            wide[wcharCount] = L'\0';

            constexpr wchar_t kResponsePrefix[] =
                L"FRAMEHANDOFF ";

            constexpr size_t kResponsePrefixChars =
                (sizeof(kResponsePrefix) /
                 sizeof(kResponsePrefix[0])) - 1;

            if (
                wcharCount < kResponsePrefixChars ||
                wcsncmp(
                    wide,
                    kResponsePrefix,
                    kResponsePrefixChars
                ) != 0
            )
            {
                // Unsolicited VDD log/control traffic on the shared pipe.
                continue;
            }

            auto parsed =
                ParseDiscoveryResponse(wide);

            if (!parsed.has_value())
            {
                if (diagnosticIndex <= 32)
                {
                    std::wcerr
                        << L"Q19B_FRAMEHANDOFF_PARSE"
                        << L" INDEX="
                        << diagnosticIndex
                        << L" RESULT=FAIL"
                        << std::endl;
                }

                break;
            }

            if (diagnosticIndex <= 32)
            {
                std::wcerr
                    << L"Q19B_FRAMEHANDOFF_PARSE"
                    << L" INDEX="
                    << diagnosticIndex
                    << L" RESULT=PASS"
                    << L" AVAILABLE="
                    << (parsed->Available ? 1 : 0)
                    << L" NAME="
                    << parsed->Name
                    << L" GENERATION="
                    << parsed->Generation
                    << L" WIDTH="
                    << parsed->Width
                    << L" HEIGHT="
                    << parsed->Height
                    << L" FORMAT="
                    << static_cast<UINT>(
                        parsed->Format
                    )
                    << L" PRODUCER_KEY="
                    << parsed->ProducerKey
                    << L" CONSUMER_KEY="
                    << parsed->ConsumerKey
                    << L" PRODUCER_LUID_HIGH="
                    << parsed->RenderAdapterLuidHigh
                    << L" PRODUCER_LUID_LOW="
                    << parsed->RenderAdapterLuidLow
                    << std::endl;
            }

            metadata = *parsed;
            discovered = true;
            break;
        }

        CloseHandle(pipe);
        return discovered;
    }

    HRESULT CreateConsumerDevice(
        const LUID* preferredAdapterLuid,
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

        ComPtr<IDXGIAdapter1> preferredAdapter;

        if (preferredAdapterLuid != nullptr)
        {
            // RAW-N8G38Q22A:
            // Diagnostic A/B: bind the consumer D3D11 device to the exact
            // render-adapter LUID emitted by the VDD producer.
            ComPtr<IDXGIFactory4> factory;

            HRESULT factoryHr =
                CreateDXGIFactory2(
                    0,
                    IID_PPV_ARGS(&factory)
                );

            if (FAILED(factoryHr))
            {
                return factoryHr;
            }

            HRESULT enumHr =
                factory->EnumAdapterByLuid(
                    *preferredAdapterLuid,
                    IID_PPV_ARGS(&preferredAdapter)
                );

            if (FAILED(enumHr))
            {
                std::wcerr
                    << L"Q22A_ENUM_ADAPTER_FAIL"
                    << L" HRESULT_DEC="
                    << static_cast<LONG>(enumHr)
                    << L" HRESULT_HEX=0x"
                    << std::hex
                    << static_cast<unsigned long>(enumHr)
                    << std::dec
                    << L" LUID_HIGH="
                    << preferredAdapterLuid->HighPart
                    << L" LUID_LOW="
                    << preferredAdapterLuid->LowPart
                    << std::endl;

                return enumHr;
            }

            DXGI_ADAPTER_DESC1 preferredDesc = {};

            if (SUCCEEDED(preferredAdapter->GetDesc1(&preferredDesc)))
            {
                std::wcerr
                    << L"Q22A_SELECTED_PRODUCER_ADAPTER"
                    << L" LUID_HIGH="
                    << preferredDesc.AdapterLuid.HighPart
                    << L" LUID_LOW="
                    << preferredDesc.AdapterLuid.LowPart
                    << L" DESCRIPTION="
                    << preferredDesc.Description
                    << std::endl;
            }
        }

        IDXGIAdapter* adapterForDevice =
            preferredAdapter.Get();

        D3D_DRIVER_TYPE driverType =
            adapterForDevice != nullptr
                ? D3D_DRIVER_TYPE_UNKNOWN
                : D3D_DRIVER_TYPE_HARDWARE;

        HRESULT hr = D3D11CreateDevice(
            adapterForDevice,
            driverType,
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
                adapterForDevice,
                driverType,
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

        // RAW-N8G38Q20B:
        // Record the actual DXGI adapter selected by the consumer's
        // default D3D11CreateDevice(nullptr, HARDWARE, ...) path.
        ComPtr<IDXGIDevice> dxgiDevice;
        ComPtr<IDXGIAdapter> dxgiAdapter;

        HRESULT adapterHr =
            baseDevice.As(&dxgiDevice);

        if (SUCCEEDED(adapterHr))
        {
            adapterHr =
                dxgiDevice->GetAdapter(
                    &dxgiAdapter
                );
        }

        if (SUCCEEDED(adapterHr))
        {
            DXGI_ADAPTER_DESC adapterDesc = {};

            adapterHr =
                dxgiAdapter->GetDesc(
                    &adapterDesc
                );

            if (SUCCEEDED(adapterHr))
            {
                std::wcerr
                    << L"Q20B_CONSUMER_ADAPTER"
                    << L" LUID_HIGH="
                    << adapterDesc.AdapterLuid.HighPart
                    << L" LUID_LOW="
                    << adapterDesc.AdapterLuid.LowPart
                    << L" DESCRIPTION="
                    << adapterDesc.Description
                    << std::endl;
            }
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
            static LONG openFailureCount = 0;

            const LONG failureIndex =
                InterlockedIncrement(
                    &openFailureCount
                );

            if (failureIndex <= 16)
            {
                std::wcerr
                    << L"Q20B_OPEN_SHARED_FAIL"
                    << L" INDEX="
                    << failureIndex
                    << L" HRESULT_DEC="
                    << static_cast<LONG>(hr)
                    << L" HRESULT_HEX=0x"
                    << std::hex
                    << static_cast<unsigned long>(hr)
                    << std::dec
                    << L" NAME="
                    << metadata.Name
                    << std::endl;
            }

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
            std::wcerr
                << L"Q20B_DESC_MISMATCH"
                << L" ACTUAL_WIDTH="
                << desc.Width
                << L" ACTUAL_HEIGHT="
                << desc.Height
                << L" ACTUAL_FORMAT="
                << static_cast<UINT>(desc.Format)
                << L" EXPECTED_WIDTH="
                << metadata.Width
                << L" EXPECTED_HEIGHT="
                << metadata.Height
                << L" EXPECTED_FORMAT="
                << static_cast<UINT>(
                    metadata.Format
                )
                << std::endl;

            texture.Reset();
            return E_INVALIDARG;
        }

        HRESULT mutexHr =
            texture.As(&mutex);

        if (FAILED(mutexHr))
        {
            std::wcerr
                << L"Q20B_MUTEX_QI_FAIL"
                << L" HRESULT_DEC="
                << static_cast<LONG>(mutexHr)
                << L" HRESULT_HEX=0x"
                << std::hex
                << static_cast<unsigned long>(mutexHr)
                << std::dec
                << std::endl;
        }
        else
        {
            std::wcerr
                << L"Q20B_OPEN_SHARED_PASS"
                << L" WIDTH="
                << desc.Width
                << L" HEIGHT="
                << desc.Height
                << L" FORMAT="
                << static_cast<UINT>(desc.Format)
                << std::endl;
        }

        return mutexHr;
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

    const LUID producerAdapterLuid =
    {
        100708,
        0
    };

    std::wcerr
        << L"Q22A_REQUESTED_PRODUCER_ADAPTER"
        << L" LUID_HIGH="
        << producerAdapterLuid.HighPart
        << L" LUID_LOW="
        << producerAdapterLuid.LowPart
        << std::endl;

    HRESULT hr = CreateConsumerDevice(
        &producerAdapterLuid,
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
