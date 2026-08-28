"""
Khan Cloud gaming display-policy selector.

KG-008K22F1

This module belongs to the control-plane scheduling layer. It translates
scheduler/session capability constraints into the runtime-policy contract
consumed by the Khan Node Agent.

The driver is NOT the business-policy engine.

For the K22 production baseline the selector is deliberately constrained to
the historical, Windows-validated 14-mode VDD regression envelope.

Future expansion beyond these modes requires a separately validated VDD
capability checkpoint.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Iterable


CONTRACT_VERSION = "kg008k-runtime-policy-v1"
SELECTOR_VERSION = "kg008k22-display-selector-v1"


class GamingDisplayPolicyError(ValueError):
    """Raised when scheduler display constraints cannot produce a safe policy."""


@dataclass(frozen=True, order=True)
class DisplayMode:
    width: int
    height: int
    refresh_hz: int

    def to_payload(self) -> dict[str, int]:
        return {
            "width": self.width,
            "height": self.height,
            "refresh_hz": self.refresh_hz,
        }


HISTORICAL_14_MODES: tuple[DisplayMode, ...] = (
    DisplayMode(1280, 720, 30),
    DisplayMode(1280, 720, 60),
    DisplayMode(1920, 1080, 60),
    DisplayMode(1920, 1080, 120),
    DisplayMode(1920, 1080, 144),
    DisplayMode(1920, 1080, 165),
    DisplayMode(1920, 1080, 240),
    DisplayMode(2560, 1440, 60),
    DisplayMode(2560, 1440, 120),
    DisplayMode(2560, 1440, 144),
    DisplayMode(2560, 1440, 165),
    DisplayMode(2560, 1440, 240),
    DisplayMode(3840, 2160, 60),
    DisplayMode(3840, 2160, 120),
)


@dataclass(frozen=True)
class DisplayPolicyConstraints:
    """
    Effective scheduler constraints for one gaming session.

    These constraints should already represent the intersection of:
    - game/title requirements;
    - GPU/encoder capability;
    - customer product entitlement;
    - client/display capability;
    - current network policy.
    """

    max_width: int = 3840
    max_height: int = 2160
    max_refresh_hz: int = 240

    min_width: int = 1280
    min_height: int = 720
    min_refresh_hz: int = 30

    preferred_width: int | None = None
    preferred_height: int | None = None
    preferred_refresh_hz: int | None = None

    hdr_requested: bool = False
    hdr_capable: bool = False

    allow_4k: bool = True
    allow_240hz: bool = True

    def validate(self) -> None:
        if self.min_width <= 0 or self.min_height <= 0:
            raise GamingDisplayPolicyError(
                "Minimum display dimensions must be positive."
            )

        if self.max_width <= 0 or self.max_height <= 0:
            raise GamingDisplayPolicyError(
                "Maximum display dimensions must be positive."
            )

        if self.min_width > self.max_width:
            raise GamingDisplayPolicyError(
                "min_width cannot exceed max_width."
            )

        if self.min_height > self.max_height:
            raise GamingDisplayPolicyError(
                "min_height cannot exceed max_height."
            )

        if self.min_refresh_hz <= 0:
            raise GamingDisplayPolicyError(
                "min_refresh_hz must be positive."
            )

        if self.max_refresh_hz <= 0:
            raise GamingDisplayPolicyError(
                "max_refresh_hz must be positive."
            )

        if self.min_refresh_hz > self.max_refresh_hz:
            raise GamingDisplayPolicyError(
                "min_refresh_hz cannot exceed max_refresh_hz."
            )

        preferred = (
            self.preferred_width,
            self.preferred_height,
            self.preferred_refresh_hz,
        )

        populated = sum(value is not None for value in preferred)

        if populated not in (0, 3):
            raise GamingDisplayPolicyError(
                "Preferred display mode must specify width, height, "
                "and refresh together."
            )


def _mode_allowed(
    mode: DisplayMode,
    constraints: DisplayPolicyConstraints,
) -> bool:
    if mode.width < constraints.min_width:
        return False

    if mode.height < constraints.min_height:
        return False

    if mode.refresh_hz < constraints.min_refresh_hz:
        return False

    if mode.width > constraints.max_width:
        return False

    if mode.height > constraints.max_height:
        return False

    if mode.refresh_hz > constraints.max_refresh_hz:
        return False

    if not constraints.allow_4k and mode.width >= 3840:
        return False

    if not constraints.allow_240hz and mode.refresh_hz >= 240:
        return False

    return True


def allowed_modes(
    constraints: DisplayPolicyConstraints,
    *,
    capability_envelope: Iterable[DisplayMode] = HISTORICAL_14_MODES,
) -> tuple[DisplayMode, ...]:
    constraints.validate()

    modes = tuple(
        sorted(
            mode
            for mode in capability_envelope
            if _mode_allowed(mode, constraints)
        )
    )

    if not modes:
        raise GamingDisplayPolicyError(
            "Display constraints produced no validated VDD modes."
        )

    return modes


def _preferred_mode(
    modes: tuple[DisplayMode, ...],
    constraints: DisplayPolicyConstraints,
) -> DisplayMode:
    explicit = (
        constraints.preferred_width is not None
        and constraints.preferred_height is not None
        and constraints.preferred_refresh_hz is not None
    )

    if explicit:
        requested = DisplayMode(
            constraints.preferred_width,
            constraints.preferred_height,
            constraints.preferred_refresh_hz,
        )

        if requested not in modes:
            raise GamingDisplayPolicyError(
                "Requested preferred display mode is not present in the "
                "effective validated mode set."
            )

        return requested

    # Automatic scheduler preference:
    #
    # 1. Prefer higher resolution.
    # 2. Then prefer higher refresh.
    #
    # Because the set is already restricted by product/game/GPU/client/network
    # constraints, the highest remaining mode represents the best permitted
    # experience without exposing raw hardware policy to the driver.
    return max(
        modes,
        key=lambda mode: (
            mode.width * mode.height,
            mode.refresh_hz,
        ),
    )


def _policy_version(
    *,
    modes: tuple[DisplayMode, ...],
    preferred: DisplayMode,
    hdr_enabled: bool,
    bit_depth: int,
    color_space: str,
) -> str:
    canonical = {
        "selector": SELECTOR_VERSION,
        "modes": [
            mode.to_payload()
            for mode in modes
        ],
        "preferred_mode": preferred.to_payload(),
        "hdr_enabled": hdr_enabled,
        "bit_depth": bit_depth,
        "color_space": color_space,
    }

    encoded = json.dumps(
        canonical,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    digest = hashlib.sha256(encoded).hexdigest()[:20]

    return f"{SELECTOR_VERSION}-{digest}"


def derive_display_policy(
    constraints: DisplayPolicyConstraints,
) -> dict[str, object]:
    """
    Produce the exact runtime-policy payload consumed by Node Agent.

    HDR remains fail-safe:
    - SDR is always available.
    - HDR is emitted only when both requested AND capability-approved.
    - Operational HDR still requires separate Windows Advanced Color and
      Sunshine/Moonlight end-to-end validation.
    """

    modes = allowed_modes(constraints)

    preferred = _preferred_mode(
        modes,
        constraints,
    )

    hdr_enabled = (
        constraints.hdr_requested
        and constraints.hdr_capable
    )

    if hdr_enabled:
        bit_depth = 10
        color_space = "Rec.2020"
    else:
        bit_depth = 8
        color_space = "RGB"

    version = _policy_version(
        modes=modes,
        preferred=preferred,
        hdr_enabled=hdr_enabled,
        bit_depth=bit_depth,
        color_space=color_space,
    )

    return {
        "contract_version": CONTRACT_VERSION,
        "policy_version": version,
        "modes": [
            mode.to_payload()
            for mode in modes
        ],
        "preferred_mode": preferred.to_payload(),
        "hdr_enabled": hdr_enabled,
        "bit_depth": bit_depth,
        "color_space": color_space,
    }


def attach_display_policy(
    session_payload: dict[str, object],
    constraints: DisplayPolicyConstraints,
) -> dict[str, object]:
    """
    Return a new gaming.session.create payload carrying the derived policy.

    The input dictionary is not mutated.
    """

    result = dict(session_payload)

    if "display_policy" in result:
        raise GamingDisplayPolicyError(
            "Session payload already contains display_policy."
        )

    result["display_policy"] = derive_display_policy(
        constraints
    )

    return result
