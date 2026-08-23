#pragma once

#include <Windows.h>
#include <array>

namespace KhanDisplay
{
    struct Mode
    {
        DWORD Width;
        DWORD Height;
        DWORD RefreshHz;
        bool CustomerVisible;
    };

    //
    // Canonical Khan Cloud display ladder.
    //
    // Customer-visible preferred tiers:
    //
    // Standard = 1920x1080@60
    // High     = 2560x1440@120
    // Ultra    = 3840x2160@60
    //
    // Remaining modes exist for adaptive degradation/recovery.
    //
    inline constexpr std::array<Mode, 7> Modes =
    {{
        { 3840, 2160,  60, true  },
        { 2560, 1440, 120, true  },
        { 2560, 1440,  60, false },
        { 1920, 1080, 120, false },
        { 1920, 1080,  60, true  },
        { 1280,  720,  60, false },
        { 1280,  720,  30, false },
    }};

    inline constexpr DWORD DefaultWidth = 1920;
    inline constexpr DWORD DefaultHeight = 1080;
    inline constexpr DWORD DefaultRefreshHz = 60;

    //
    // HDR/WCG architecture policy.
    //
    // This does NOT claim HDR is functional until Windows installation
    // validation proves the driver is advertised and accepted as HDR-capable.
    //
    inline constexpr bool HdrArchitectureEnabled = true;
    inline constexpr unsigned int SdrBitsPerComponent = 8;
    inline constexpr unsigned int HdrBitsPerComponent = 10;
}
