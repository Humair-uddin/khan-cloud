"""
Khan Virtual Display runtime-policy compatibility surface.

The authoritative production implementation is owned by the Khan Cloud
Node Agent:

    khan_agent.vdd_runtime_policy

KG-008K22 deliberately keeps one runtime-policy implementation.  The VDD
repository exposes this compatibility module for source-side validation and
tooling without maintaining a second copy of validation, XML generation,
atomic deployment, or last-known-good recovery logic.
"""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
NODE_AGENT_ROOT = REPO_ROOT / "node-agent"

if str(NODE_AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(NODE_AGENT_ROOT))

from khan_agent.vdd_runtime_policy import (  # noqa: E402,F401
    CONTRACT_VERSION,
    LKG_NAME,
    MAX_HEIGHT,
    MAX_REFRESH_HZ,
    MAX_WIDTH,
    MIN_HEIGHT,
    MIN_REFRESH_HZ,
    MIN_WIDTH,
    STATE_NAME,
    TARGET_NAME,
    DisplayMode,
    RuntimeDisplayPolicy,
    VddRuntimePolicyError,
    apply_display_policy,
    apply_policy_atomic as _canonical_apply_policy_atomic,
    policy_from_payload,
    render_settings_xml,
    restore_last_known_good as _canonical_restore_last_known_good,
)


def apply_policy_atomic(
    *,
    template=None,
    template_path=None,
    target_root,
    policy,
):
    """
    Compatibility adapter for the pre-consolidation VDD API.

    Historical VDD tooling used `template=`.
    The canonical Node Agent implementation uses
    `template_path=`. Both are accepted here while all real
    implementation remains in khan_agent.vdd_runtime_policy.
    """

    if template is not None and template_path is not None:
        raise TypeError(
            "Specify only one of template or template_path"
        )

    resolved_template = (
        template_path
        if template_path is not None
        else template
    )

    if resolved_template is None:
        raise TypeError(
            "template or template_path is required"
        )

    return _canonical_apply_policy_atomic(
        template_path=resolved_template,
        target_root=target_root,
        policy=policy,
    )



def restore_last_known_good(
    target_root=None,
    *,
    root=None,
):
    """
    Compatibility adapter for historical VDD callers.

    Legacy tooling passed target_root positionally.
    The canonical Node Agent implementation keeps a keyword-only API.
    """

    if target_root is not None and root is not None:
        raise TypeError(
            "Specify only one of target_root or root"
        )

    resolved_root = (
        root
        if root is not None
        else target_root
    )

    if resolved_root is None:
        raise TypeError(
            "target_root is required"
        )

    return _canonical_restore_last_known_good(
        target_root=resolved_root,
    )

# Historical VDD-side callers used SETTINGS_NAME.
SETTINGS_NAME = TARGET_NAME

__all__ = [
    "CONTRACT_VERSION",
    "SETTINGS_NAME",
    "STATE_NAME",
    "LKG_NAME",
    "MIN_WIDTH",
    "MIN_HEIGHT",
    "MAX_WIDTH",
    "MAX_HEIGHT",
    "MIN_REFRESH_HZ",
    "MAX_REFRESH_HZ",
    "DisplayMode",
    "RuntimeDisplayPolicy",
    "VddRuntimePolicyError",
    "policy_from_payload",
    "render_settings_xml",
    "apply_policy_atomic",
    "apply_display_policy",
    "restore_last_known_good",
]
