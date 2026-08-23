# Driver implementation

Target architecture:

- Windows 11
- x64
- UMDF
- IddCx
- Visual Studio / WDK

Planned functional units:

- device/adapter initialization
- IddCx adapter registration
- monitor arrival/removal
- monitor description / EDID policy
- supported mode enumeration
- active-mode tracking
- swap-chain/frame processing required by IddCx
- Khan control-channel integration
- health telemetry

Implementation begins only after pinned upstream source review.
