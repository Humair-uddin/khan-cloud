from __future__ import annotations

import inspect

import hashlib
import json
import os
import shutil
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any


CONTRACT_VERSION = "kg008k-runtime-policy-v1"

MIN_WIDTH = 1280
MIN_HEIGHT = 720
MAX_WIDTH = 3840
MAX_HEIGHT = 2160
MIN_REFRESH_HZ = 24
MAX_REFRESH_HZ = 240

TARGET_NAME = "khan-vdd-settings.xml"
STATE_NAME = "runtime-policy-state.json"
LKG_NAME = "khan-vdd-settings.last-known-good.xml"


class VddRuntimePolicyError(ValueError):
    pass


@dataclass(frozen=True, order=True)
class DisplayMode:
    width: int
    height: int
    refresh_hz: int

    def validate(self) -> None:
        if not MIN_WIDTH <= self.width <= MAX_WIDTH:
            raise VddRuntimePolicyError(
                f"display width must be between {MIN_WIDTH} and {MAX_WIDTH}"
            )

        if not MIN_HEIGHT <= self.height <= MAX_HEIGHT:
            raise VddRuntimePolicyError(
                f"display height must be between {MIN_HEIGHT} and {MAX_HEIGHT}"
            )

        if not MIN_REFRESH_HZ <= self.refresh_hz <= MAX_REFRESH_HZ:
            raise VddRuntimePolicyError(
                f"display refresh_hz must be between "
                f"{MIN_REFRESH_HZ} and {MAX_REFRESH_HZ}"
            )


@dataclass(frozen=True)
class RuntimeDisplayPolicy:
    policy_version: str
    modes: tuple[DisplayMode, ...]
    preferred_mode: DisplayMode
    hdr_enabled: bool = False
    bit_depth: int = 10
    color_space: str = "RGB"
    policy_id: str | None = None
    revision: int | None = None

    def validate(self) -> None:
        if not self.policy_version.strip():
            raise VddRuntimePolicyError(
                "display policy_version is required"
            )

        if (
            self.policy_id is None
            and self.revision is not None
        ):
            raise VddRuntimePolicyError(
                "display policy_id is required when revision is supplied"
            )

        if (
            self.policy_id is not None
            and self.revision is None
        ):
            raise VddRuntimePolicyError(
                "display revision is required when policy_id is supplied"
            )

        if self.policy_id is not None:
            if not self.policy_id.strip():
                raise VddRuntimePolicyError(
                    "display policy_id must not be empty"
                )

            if (
                isinstance(self.revision, bool)
                or not isinstance(self.revision, int)
                or self.revision < 1
            ):
                raise VddRuntimePolicyError(
                    "display revision must be a positive integer"
                )

        if not self.modes:
            raise VddRuntimePolicyError(
                "display policy requires at least one mode"
            )

        for mode in self.modes:
            mode.validate()

        if len(set(self.modes)) != len(self.modes):
            raise VddRuntimePolicyError(
                "display policy contains duplicate modes"
            )

        self.preferred_mode.validate()

        if self.preferred_mode not in self.modes:
            raise VddRuntimePolicyError(
                "preferred display mode must be in allowed modes"
            )

        if self.bit_depth not in (8, 10):
            raise VddRuntimePolicyError(
                "display bit_depth must be 8 or 10"
            )

        if self.hdr_enabled and self.bit_depth != 10:
            raise VddRuntimePolicyError(
                "HDR display policy requires 10-bit output"
            )

        if self.color_space not in ("RGB", "Rec.2020"):
            raise VddRuntimePolicyError(
                "display color_space must be RGB or Rec.2020"
            )

        if self.hdr_enabled and self.color_space != "Rec.2020":
            raise VddRuntimePolicyError(
                "HDR display policy requires Rec.2020"
            )


def _integer(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise VddRuntimePolicyError(
            f"{field} must be an integer"
        )

    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise VddRuntimePolicyError(
            f"{field} must be an integer"
        ) from exc


def _mode_from_payload(
    value: Any,
    *,
    field: str,
) -> DisplayMode:
    if not isinstance(value, dict):
        raise VddRuntimePolicyError(
            f"{field} must be an object"
        )

    mode = DisplayMode(
        width=_integer(value.get("width"), f"{field}.width"),
        height=_integer(value.get("height"), f"{field}.height"),
        refresh_hz=_integer(
            value.get("refresh_hz"),
            f"{field}.refresh_hz",
        ),
    )

    mode.validate()
    return mode


def policy_from_payload(
    payload: dict[str, Any],
) -> RuntimeDisplayPolicy:
    policy_version = str(
        payload.get("policy_version") or ""
    ).strip()

    raw_policy_id = payload.get(
        "policy_id"
    )
    raw_revision = payload.get(
        "revision"
    )

    if (
        raw_policy_id is None
        and raw_revision is None
    ):
        policy_id = None
        revision = None

    elif (
        raw_policy_id is None
        or raw_revision is None
    ):
        raise VddRuntimePolicyError(
            "display policy_id and revision must be supplied together"
        )

    else:
        policy_id = str(
            raw_policy_id
        ).strip()

        revision = _integer(
            raw_revision,
            "revision",
        )

    raw_modes = payload.get("modes")

    if not isinstance(raw_modes, list):
        raise VddRuntimePolicyError(
            "display modes must be an array"
        )

    modes = tuple(
        _mode_from_payload(
            item,
            field=f"modes[{index}]",
        )
        for index, item in enumerate(raw_modes)
    )

    preferred = _mode_from_payload(
        payload.get("preferred_mode"),
        field="preferred_mode",
    )

    hdr_enabled = payload.get("hdr_enabled", False)

    if not isinstance(hdr_enabled, bool):
        raise VddRuntimePolicyError(
            "hdr_enabled must be a boolean"
        )

    policy = RuntimeDisplayPolicy(
        policy_version=policy_version,
        modes=modes,
        preferred_mode=preferred,
        hdr_enabled=hdr_enabled,
        policy_id=policy_id,
        revision=revision,
        bit_depth=_integer(
            payload.get("bit_depth", 10),
            "bit_depth",
        ),
        color_space=str(
            payload.get("color_space") or "RGB"
        ).strip(),
    )

    policy.validate()
    return policy


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def _find_resolutions(root: ET.Element) -> ET.Element:
    resolutions = root.find(".//resolutions")

    if resolutions is None:
        raise VddRuntimePolicyError(
            "VDD template is missing <resolutions>"
        )

    return resolutions


def _set_text(
    root: ET.Element,
    xpath: str,
    value: str,
) -> None:
    node = root.find(xpath)

    if node is not None:
        node.text = value


def render_settings_xml(
    template_path: Path,
    policy: RuntimeDisplayPolicy,
) -> bytes:
    policy.validate()

    try:
        tree = ET.parse(template_path)
    except (OSError, ET.ParseError) as exc:
        raise VddRuntimePolicyError(
            f"VDD template is unreadable: {template_path}"
        ) from exc

    root = tree.getroot()
    resolutions = _find_resolutions(root)

    for child in list(resolutions):
        resolutions.remove(child)

    for mode in policy.modes:
        node = ET.SubElement(resolutions, "resolution")
        ET.SubElement(node, "width").text = str(mode.width)
        ET.SubElement(node, "height").text = str(mode.height)
        ET.SubElement(node, "refresh_rate").text = str(
            mode.refresh_hz
        )

    _set_text(
        root,
        ".//colour/SDR10bit",
        "true" if policy.bit_depth == 10 else "false",
    )

    _set_text(
        root,
        ".//hdr_advanced/enabled",
        "true" if policy.hdr_enabled else "false",
    )

    _set_text(
        root,
        ".//color_advanced/force_bit_depth",
        str(policy.bit_depth),
    )

    _set_text(
        root,
        ".//color_advanced/primary_color_space",
        policy.color_space,
    )

    xml = ET.tostring(
        root,
        encoding="utf-8",
        xml_declaration=True,
    )

    return xml + b"\n"



def _transaction_file_snapshot(
    path: Path,
) -> tuple[bool, bytes]:
    """Capture exact pre-transaction file state."""

    path = Path(path)

    if not path.exists():
        return False, b""

    return True, path.read_bytes()


def _restore_transaction_file(
    path: Path,
    snapshot: tuple[bool, bytes],
) -> None:
    """
    Restore exact pre-transaction state.

    Files that did not exist before the transaction are removed.
    """

    path = Path(path)
    existed, content = snapshot

    if existed:
        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        path.write_bytes(content)
        return

    try:
        path.unlink()
    except FileNotFoundError:
        pass


def _runtime_transaction_paths(
    target_root: Path,
) -> tuple[Path, Path, Path]:
    root = Path(target_root)

    return (
        root / "khan-vdd-settings.xml",
        root / STATE_NAME,
        root / LKG_NAME,
    )


def _capture_runtime_transaction(
    target_root: Path,
) -> dict[Path, tuple[bool, bytes]]:
    return {
        path: _transaction_file_snapshot(path)
        for path in _runtime_transaction_paths(
            target_root
        )
    }


def _rollback_runtime_transaction(
    snapshots: dict[
        Path,
        tuple[bool, bytes],
    ],
) -> None:
    errors: list[str] = []

    for path, snapshot in snapshots.items():
        try:
            _restore_transaction_file(
                path,
                snapshot,
            )
        except Exception as exc:
            errors.append(
                f"{path}: {exc}"
            )

    if errors:
        raise VddRuntimePolicyError(
            "VDD runtime-policy rollback failed: "
            + "; ".join(errors)
        )


def _canonical_policy_payload(
    policy: RuntimeDisplayPolicy,
) -> dict[str, Any]:
    """
    Logical policy content used for replay identity.

    Delivery-order metadata (policy_id and revision) is deliberately
    excluded from the fingerprint.
    """

    return {
        "policy_version": policy.policy_version,
        "modes": [
            {
                "width": mode.width,
                "height": mode.height,
                "refresh_hz": mode.refresh_hz,
            }
            for mode in policy.modes
        ],
        "preferred_mode": {
            "width": policy.preferred_mode.width,
            "height": policy.preferred_mode.height,
            "refresh_hz": policy.preferred_mode.refresh_hz,
        },
        "hdr_enabled": policy.hdr_enabled,
        "bit_depth": policy.bit_depth,
        "color_space": policy.color_space,
    }


def _policy_fingerprint(
    policy: RuntimeDisplayPolicy,
) -> str:
    canonical = json.dumps(
        _canonical_policy_payload(policy),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    return _sha256(canonical)


def _load_policy_state(
    state_path: Path,
) -> dict[str, Any] | None:
    state_path = Path(state_path)

    if not state_path.exists():
        return None

    try:
        payload = json.loads(
            state_path.read_text(
                encoding="utf-8"
            )
        )
    except Exception as exc:
        raise VddRuntimePolicyError(
            "Existing VDD runtime-policy state is unreadable"
        ) from exc

    if not isinstance(payload, dict):
        raise VddRuntimePolicyError(
            "Existing VDD runtime-policy state must be an object"
        )

    return payload


def _revision_guard(
    *,
    state_path: Path,
    target_path: Path,
    policy: RuntimeDisplayPolicy,
    fingerprint: str,
) -> dict[str, Any] | None:
    """
    Enforce monotonic ordering within one policy_id stream.

    Different policy_id values represent a new independently bound
    policy stream. Existing gaming-session idempotency separately
    prevents an existing session from silently changing its binding.
    """

    # Legacy compatibility calls that do not carry ordering metadata
    # retain their historical replace/LKG semantics. Production gaming
    # policies always carry both policy_id and revision.
    if (
        policy.policy_id is None
        and policy.revision is None
    ):
        return None

    previous = _load_policy_state(
        state_path
    )

    if previous is None:
        return None

    previous_id = previous.get(
        "policy_id"
    )

    # State produced before the revision contract remains upgradeable.
    if previous_id is None:
        return None

    if str(previous_id) != policy.policy_id:
        return None

    try:
        previous_revision = int(
            previous["revision"]
        )
    except Exception as exc:
        raise VddRuntimePolicyError(
            "Existing VDD runtime-policy revision is invalid"
        ) from exc

    previous_fingerprint = str(
        previous.get(
            "policy_fingerprint"
        )
        or ""
    )

    if policy.revision < previous_revision:
        raise VddRuntimePolicyError(
            "Stale VDD runtime policy rejected: "
            f"received revision {policy.revision}, "
            f"current revision {previous_revision}"
        )

    if policy.revision > previous_revision:
        return None

    if fingerprint != previous_fingerprint:
        raise VddRuntimePolicyError(
            "Conflicting VDD runtime policy replay rejected: "
            "same policy_id and revision contain different content"
        )

    if not target_path.exists():
        raise VddRuntimePolicyError(
            "Idempotent VDD runtime-policy replay cannot be accepted "
            "because the active settings file is missing"
        )

    expected_settings_hash = str(
        previous.get(
            "settings_sha256"
        )
        or ""
    )

    actual_settings_hash = _sha256(
        target_path.read_bytes()
    )

    if (
        not expected_settings_hash
        or actual_settings_hash
        != expected_settings_hash
    ):
        raise VddRuntimePolicyError(
            "Idempotent VDD runtime-policy replay cannot be accepted "
            "because active settings do not match persisted state"
        )

    return {
        **previous,
        "idempotent": True,
    }

def _apply_policy_atomic_unprotected(
    *,
    template_path: Path,
    target_root: Path,
    policy: RuntimeDisplayPolicy,
) -> dict[str, Any]:
    policy.validate()

    target_root = Path(target_root)
    target_root.mkdir(parents=True, exist_ok=True)

    target = target_root / TARGET_NAME
    state = target_root / STATE_NAME
    lkg = target_root / LKG_NAME

    policy_fingerprint = _policy_fingerprint(
        policy
    )

    replay = _revision_guard(
        state_path=state,
        target_path=target,
        policy=policy,
        fingerprint=policy_fingerprint,
    )

    if replay is not None:
        return replay

    payload = render_settings_xml(
        Path(template_path),
        policy,
    )

    temporary = target.with_suffix(".xml.new")
    temporary.write_bytes(payload)

    if target.exists():
        lkg_tmp = lkg.with_suffix(".xml.new")
        shutil.copy2(target, lkg_tmp)
        os.replace(lkg_tmp, lkg)

    os.replace(temporary, target)

    state_payload = {
        "contract_version": CONTRACT_VERSION,
        "policy_version": policy.policy_version,
        "settings_sha256": _sha256(payload),
        "mode_count": len(policy.modes),
        "modes": [
            {
                "width": mode.width,
                "height": mode.height,
                "refresh_hz": mode.refresh_hz,
            }
            for mode in policy.modes
        ],
        "preferred_mode": {
            "width": policy.preferred_mode.width,
            "height": policy.preferred_mode.height,
            "refresh_hz": policy.preferred_mode.refresh_hz,
        },
        "hdr_enabled": policy.hdr_enabled,
        "bit_depth": policy.bit_depth,
        "color_space": policy.color_space,
    }

    if (
        policy.policy_id is not None
        and policy.revision is not None
    ):
        state_payload["policy_id"] = (
            policy.policy_id
        )
        state_payload["revision"] = (
            policy.revision
        )
        state_payload["policy_fingerprint"] = (
            policy_fingerprint
        )

    state_tmp = state.with_suffix(".json.new")
    state_tmp.write_text(
        json.dumps(
            state_payload,
            indent=2,
            sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )
    os.replace(state_tmp, state)

    return state_payload


def apply_policy_atomic(*args, **kwargs):
    """
    Transactional facade for the canonical runtime-policy apply.

    Argument binding is delegated to the original canonical function's
    actual Python signature. This avoids maintaining a second signature
    or a second policy implementation.
    """

    signature = inspect.signature(
        _apply_policy_atomic_unprotected
    )

    bound = signature.bind(
        *args,
        **kwargs,
    )

    bound.apply_defaults()

    if "target_root" not in bound.arguments:
        raise VddRuntimePolicyError(
            "Runtime policy target_root is required."
        )

    target_root = Path(
        bound.arguments["target_root"]
    )

    snapshots = _capture_runtime_transaction(
        target_root
    )

    try:
        return _apply_policy_atomic_unprotected(
            *args,
            **kwargs,
        )

    except Exception as apply_error:
        try:
            _rollback_runtime_transaction(
                snapshots
            )

        except Exception as rollback_error:
            raise VddRuntimePolicyError(
                "VDD runtime-policy apply failed and "
                "rollback also failed. "
                f"apply={apply_error}; "
                f"rollback={rollback_error}"
            ) from rollback_error

        raise


# Preserve introspection compatibility for callers and tests.
apply_policy_atomic.__signature__ = inspect.signature(
    _apply_policy_atomic_unprotected
)


def apply_display_policy(
    payload: dict[str, Any],
    *,
    template_path: Path,
    target_root: Path,
) -> dict[str, Any]:
    policy = policy_from_payload(payload)

    result = apply_policy_atomic(
        template_path=template_path,
        target_root=target_root,
        policy=policy,
    )

    return {
        **result,
        "settings_path": str(
            Path(target_root) / TARGET_NAME
        ),
        "last_known_good_available": (
            Path(target_root) / LKG_NAME
        ).exists(),
    }


def restore_last_known_good(
    *,
    target_root: Path,
) -> Path:
    target_root = Path(target_root)
    target = target_root / TARGET_NAME
    lkg = target_root / LKG_NAME

    if not lkg.exists():
        raise VddRuntimePolicyError(
            "No VDD last-known-good policy is available"
        )

    recovery = target.with_suffix(".xml.recovery")
    shutil.copy2(lkg, recovery)
    os.replace(recovery, target)

    return target
