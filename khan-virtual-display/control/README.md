# Khan Display Control

This layer provides the stable boundary between Khan Guest Agent and the
Windows display driver.

Adaptive-stream policy does not belong in the driver.

The future flow is:

Khan Quality Controller
        |
        v
Khan Guest Agent
        |
        v
Khan Display Control
        |
        v
Khan Virtual Display Driver

The controller can request a supported display mode when bitrate/FPS
degradation alone is insufficient.
