# Khan Virtual Display

Khan Virtual Display is the headless display component for Khan Cloud gaming
VMs.

## Runtime role

The driver creates a Windows virtual monitor using Microsoft's supported
Indirect Display Driver architecture / IddCx framework.

It does not perform video streaming.

Runtime separation:

    Game
      |
      v
    Khan Virtual Display
      |
      v
    Windows rendered display
      |
      v
    Khan Streaming Runtime
      |
      v
    customer client

## Design goals

- Windows 11 gaming VM support.
- Headless operation.
- Deterministic virtual-monitor creation.
- Khan-controlled resolution and refresh rate.
- Standard / High / Ultra customer profiles.
- Internal adaptive fallback modes.
- Health/status query from Khan Guest Agent.
- No customer-facing display-driver UI.
- Future HDR capability.
- Future dynamic mode transition coordinated with Khan Quality Controller.

## Ownership boundary

The driver is a new Khan-owned codebase.

Microsoft Windows-driver-samples and VirtualDrivers VDD are upstream
references. Upstream source must not be imported without provenance and
license review.

## Initial milestone

KG-008K establishes:

1. repository structure;
2. pinned upstream revisions;
3. licensing provenance;
4. display mode contract;
5. Guest Agent control protocol.

No upstream C/C++ implementation code is imported in this milestone.
