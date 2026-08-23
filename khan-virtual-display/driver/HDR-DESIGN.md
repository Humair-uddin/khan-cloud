# Khan Virtual Display — HDR/WCG design contract

HDR is part of the initial Khan Virtual Display architecture.

V1 compatibility policy:

- SDR must always remain available.
- HDR target path is 10 bits per component.
- Windows HDR capability is not considered implemented merely because the
  driver architecture and this design contract allow for HDR support.
- HDR becomes production-ready only after Windows reports the virtual display
  as HDR capable and the complete streaming chain passes validation.

Required future implementation work:

1. IddCx version/runtime capability detection.
2. WCG/HDR target information.
3. 10-bit path validation.
4. appropriate monitor description / EDID policy.
5. HDR static metadata handling where required.
6. Windows Advanced Color/HDR detection.
7. HEVC Main10 and/or AV1 10-bit streaming validation.
8. client HDR capability negotiation.
9. automatic fallback to SDR.

Dolby Vision is not part of KG-008K3.

The architecture must not prevent Dolby Vision or other future HDR formats,
but those require a separate licensing and end-to-end capability review.
