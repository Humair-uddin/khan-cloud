from __future__ import annotations

import pytest
import json
import xml.etree.ElementTree as ET
from pathlib import Path

from khan_agent.job_dispatch import execute_node_job
from khan_agent.vdd_runtime_policy import CONTRACT_VERSION


COMMON = {
    "virtualization_execution_enabled": False,
    "virtualization_storage_root": Path("/tmp/kc-vps"),
    "virtualization_base_image_path": Path("/tmp/base.qcow2"),
    "virtualization_network_name": "kc-test",
    "gaming_execution_enabled": True,
    "gaming_execution_backend": "windows_native",
    "gaming_streaming_backend": "sunshine",
}


EXPECTED_14 = (
    (1280, 720, 30),
    (1280, 720, 60),
    (1920, 1080, 60),
    (1920, 1080, 120),
    (1920, 1080, 144),
    (1920, 1080, 165),
    (1920, 1080, 240),
    (2560, 1440, 60),
    (2560, 1440, 120),
    (2560, 1440, 144),
    (2560, 1440, 165),
    (2560, 1440, 240),
    (3840, 2160, 60),
    (3840, 2160, 120),
)


def _template(path: Path) -> Path:
    path.write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<settings>
  <monitors>
    <monitor>
      <resolutions>
        <resolution>
          <width>1920</width>
          <height>1080</height>
          <refresh_rate>60</refresh_rate>
        </resolution>
      </resolutions>
    </monitor>
  </monitors>
  <colour>
    <SDR10bit>true</SDR10bit>
  </colour>
  <hdr_advanced>
    <enabled>false</enabled>
  </hdr_advanced>
  <color_advanced>
    <force_bit_depth>10</force_bit_depth>
    <primary_color_space>RGB</primary_color_space>
  </color_advanced>
</settings>
""",
        encoding="utf-8",
    )
    return path


def _policy():
    return {
        "policy_version": "scheduler-policy-1",
        "modes": [
            {
                "width": width,
                "height": height,
                "refresh_hz": refresh,
            }
            for width, height, refresh in EXPECTED_14
        ],
        "preferred_mode": {
            "width": 1920,
            "height": 1080,
            "refresh_hz": 120,
        },
        "hdr_enabled": False,
        "bit_depth": 10,
        "color_space": "RGB",
    }


def _job(job_type: str, payload: dict):
    return {
        "job_type": job_type,
        "payload": payload,
    }


def _modes(path: Path):
    root = ET.parse(path).getroot()

    return tuple(
        (
            int(node.findtext("width")),
            int(node.findtext("height")),
            int(node.findtext("refresh_rate")),
        )
        for node in root.findall(".//resolutions/resolution")
    )


def test_display_policy_job_applies_exact_14_atomically(tmp_path):
    template = _template(tmp_path / "template.xml")
    target = tmp_path / "programdata"

    result = execute_node_job(
        _job(
            "gaming.display.policy.apply",
            _policy(),
        ),
        gaming_vdd_template_path=template,
        gaming_vdd_target_root=target,
        **COMMON,
    )

    assert result.status == "succeeded"
    assert result.result["contract_version"] == CONTRACT_VERSION
    assert result.result["policy_version"] == "scheduler-policy-1"
    assert result.result["mode_count"] == 14

    settings = target / "khan-vdd-settings.xml"
    state = target / "runtime-policy-state.json"

    assert settings.exists()
    assert state.exists()
    assert _modes(settings) == EXPECTED_14

    saved = json.loads(state.read_text(encoding="utf-8"))
    assert saved["mode_count"] == 14
    assert saved["preferred_mode"] == {
        "width": 1920,
        "height": 1080,
        "refresh_hz": 120,
    }


def test_display_policy_rejects_duplicate_modes(tmp_path):
    template = _template(tmp_path / "template.xml")
    target = tmp_path / "programdata"

    policy = _policy()
    policy["modes"].append(dict(policy["modes"][0]))

    result = execute_node_job(
        _job(
            "gaming.display.policy.apply",
            policy,
        ),
        gaming_vdd_template_path=template,
        gaming_vdd_target_root=target,
        **COMMON,
    )

    assert result.status == "blocked"
    assert "duplicate" in result.error_message.lower()
    assert not (target / "khan-vdd-settings.xml").exists()


def test_preferred_mode_must_be_allowed(tmp_path):
    template = _template(tmp_path / "template.xml")
    target = tmp_path / "programdata"

    policy = _policy()
    policy["preferred_mode"] = {
        "width": 3840,
        "height": 2160,
        "refresh_hz": 240,
    }

    result = execute_node_job(
        _job(
            "gaming.display.policy.apply",
            policy,
        ),
        gaming_vdd_template_path=template,
        gaming_vdd_target_root=target,
        **COMMON,
    )

    assert result.status == "blocked"
    assert "preferred" in result.error_message.lower()


def test_hdr_policy_requires_rec2020(tmp_path):
    template = _template(tmp_path / "template.xml")
    target = tmp_path / "programdata"

    policy = _policy()
    policy["hdr_enabled"] = True
    policy["color_space"] = "RGB"

    result = execute_node_job(
        _job(
            "gaming.display.policy.apply",
            policy,
        ),
        gaming_vdd_template_path=template,
        gaming_vdd_target_root=target,
        **COMMON,
    )

    assert result.status == "blocked"
    assert "rec.2020" in result.error_message.lower()


def test_second_policy_creates_last_known_good_and_restore(tmp_path):
    template = _template(tmp_path / "template.xml")
    target = tmp_path / "programdata"

    first = _policy()

    result = execute_node_job(
        _job(
            "gaming.display.policy.apply",
            first,
        ),
        gaming_vdd_template_path=template,
        gaming_vdd_target_root=target,
        **COMMON,
    )

    assert result.status == "succeeded"

    original = (
        target / "khan-vdd-settings.xml"
    ).read_bytes()

    second = _policy()
    second["policy_version"] = "scheduler-policy-2"
    second["modes"] = [
        {
            "width": 1920,
            "height": 1080,
            "refresh_hz": 60,
        }
    ]
    second["preferred_mode"] = dict(second["modes"][0])

    result = execute_node_job(
        _job(
            "gaming.display.policy.apply",
            second,
        ),
        gaming_vdd_template_path=template,
        gaming_vdd_target_root=target,
        **COMMON,
    )

    assert result.status == "succeeded"
    assert result.result["last_known_good_available"] is True

    lkg = target / "khan-vdd-settings.last-known-good.xml"
    assert lkg.read_bytes() == original

    restored = execute_node_job(
        _job(
            "gaming.display.policy.restore",
            {},
        ),
        gaming_vdd_template_path=template,
        gaming_vdd_target_root=target,
        **COMMON,
    )

    assert restored.status == "succeeded"
    assert restored.result["restored"] is True
    assert (
        target / "khan-vdd-settings.xml"
    ).read_bytes() == original


def test_display_policy_execution_disabled_is_blocked(tmp_path):
    template = _template(tmp_path / "template.xml")

    common = dict(COMMON)
    common["gaming_execution_enabled"] = False

    result = execute_node_job(
        _job(
            "gaming.display.policy.apply",
            _policy(),
        ),
        gaming_vdd_template_path=template,
        gaming_vdd_target_root=tmp_path / "programdata",
        **common,
    )

    assert result.status == "blocked"
    assert "disabled" in result.error_message.lower()


def test_unsupported_display_policy_action_fails_closed(tmp_path):
    template = _template(tmp_path / "template.xml")

    result = execute_node_job(
        _job(
            "gaming.display.policy.destroy-everything",
            {},
        ),
        gaming_vdd_template_path=template,
        gaming_vdd_target_root=tmp_path / "programdata",
        **COMMON,
    )

    assert result.status == "failed"
    assert "unsupported" in result.error_message.lower()


@pytest.mark.source_tree_only
def test_vdd_runtime_policy_has_single_production_owner():
    repo_root = Path(__file__).resolve().parents[2]

    compatibility = (
        repo_root
        / "khan-virtual-display"
        / "control"
        / "runtime_policy.py"
    ).read_text(encoding="utf-8")

    canonical = (
        repo_root
        / "node-agent"
        / "khan_agent"
        / "vdd_runtime_policy.py"
    ).read_text(encoding="utf-8")

    assert (
        "from khan_agent.vdd_runtime_policy import"
        in compatibility
    )

    assert "class DisplayMode" not in compatibility
    assert "class RuntimeDisplayPolicy" not in compatibility

    # A thin compatibility wrapper is allowed so historical VDD
    # tooling can keep using template=. It must delegate to the
    # canonical Node Agent implementation rather than reimplement
    # validation, XML rendering, atomic promotion, or recovery.
    assert (
        "apply_policy_atomic as "
        "_canonical_apply_policy_atomic"
        in compatibility
    )
    assert (
        "return _canonical_apply_policy_atomic("
        in compatibility
    )

    assert "import xml.etree.ElementTree" not in compatibility
    assert "def render_settings_xml" not in compatibility
    assert "def policy_from_payload" not in compatibility
    assert "def apply_display_policy" not in compatibility

    # Historical VDD callers may also use a positional restore
    # helper. The compatibility wrapper is permitted only when it
    # delegates directly to the canonical Node Agent implementation.
    assert (
        "restore_last_known_good as "
        "_canonical_restore_last_known_good"
        in compatibility
    )
    assert (
        "return _canonical_restore_last_known_good("
        in compatibility
    )

    assert "class DisplayMode" in canonical
    assert "class RuntimeDisplayPolicy" in canonical
    assert "def render_settings_xml" in canonical
    assert "def apply_policy_atomic" in canonical
    assert "def apply_display_policy" in canonical
    assert "def restore_last_known_good" in canonical


def _good_session_environment(monkeypatch):
    from khan_agent import gaming_runtime

    # These are runtime-policy/session unit tests.  A real Windows
    # host may have a healthy Khan VDD, so availability probing would
    # otherwise execute pnputil /restart-device during pytest.
    # Live VDD activation is validated separately.
    monkeypatch.setattr(
        gaming_runtime,
        "live_activation_available",
        lambda: False,
    )

    from khan_agent import gaming_runtime

    monkeypatch.setattr(
        gaming_runtime,
        "locate_sunshine",
        lambda: Path("/sunshine.exe"),
    )

    monkeypatch.setattr(
        gaming_runtime,
        "probe_nvidia_gpu",
        lambda gpu_uuid: {
            "available": True,
            "uuid": gpu_uuid,
            "name": "NVIDIA RTX Test",
            "memory_total_mib": 12288,
            "driver_version": "test",
        },
    )

    monkeypatch.setattr(
        gaming_runtime,
        "secure_private_file",
        lambda path: None,
    )


def _session_job(
    session_id,
    *,
    display_policy_marker=True,
):
    payload = {
        "session_id": str(session_id),
        "gpu_uuid": "GPU-SESSION-POLICY",
        "minimum_vram_mb": 8192,
    }

    if display_policy_marker:
        payload["display_policy"] = _policy()

    return {
        "job_type": "gaming.session.create",
        "payload": payload,
    }


def test_session_create_applies_policy_before_game_launch(
    tmp_path,
    monkeypatch,
):
    from uuid import uuid4
    from khan_agent import gaming_runtime

    _good_session_environment(monkeypatch)

    template = _template(tmp_path / "template.xml")
    target = tmp_path / "programdata"

    order = []

    real_apply = gaming_runtime.apply_display_policy

    def tracked_apply(*args, **kwargs):
        order.append("policy")
        return real_apply(*args, **kwargs)

    monkeypatch.setattr(
        gaming_runtime,
        "apply_display_policy",
        tracked_apply,
    )

    def prepare(payload):
        order.append("prepare_game")
        return None

    monkeypatch.setattr(
        gaming_runtime,
        "prepare_game_launch",
        prepare,
    )

    session_id = uuid4()

    result = execute_node_job(
        _session_job(session_id),
        gaming_state_root=tmp_path / "gaming",
        gaming_vdd_template_path=template,
        gaming_vdd_target_root=target,
        **COMMON,
    )

    assert result.status == "succeeded"
    assert order == [
        "policy",
        "prepare_game",
    ]

    assert (
        result.result["display_policy"]["mode_count"]
        == 14
    )

    state_path = (
        tmp_path
        / "gaming"
        / "sessions"
        / f"kc-gaming-{session_id}.json"
    )

    saved = json.loads(
        state_path.read_text(encoding="utf-8")
    )

    assert saved["display_policy"]["mode_count"] == 14
    assert (
        saved["display_policy_request"]["policy_version"]
        == "scheduler-policy-1"
    )


def test_invalid_session_policy_blocks_before_game_launch(
    tmp_path,
    monkeypatch,
):
    from uuid import uuid4
    from khan_agent import gaming_runtime

    _good_session_environment(monkeypatch)

    template = _template(tmp_path / "template.xml")
    target = tmp_path / "programdata"

    launch_path_called = []

    monkeypatch.setattr(
        gaming_runtime,
        "prepare_game_launch",
        lambda payload: (
            launch_path_called.append(True)
            or None
        ),
    )

    session_id = uuid4()

    job = _session_job(session_id)

    job["payload"]["display_policy"]["modes"].append(
        dict(
            job["payload"]["display_policy"]["modes"][0]
        )
    )

    result = execute_node_job(
        job,
        gaming_state_root=tmp_path / "gaming",
        gaming_vdd_template_path=template,
        gaming_vdd_target_root=target,
        **COMMON,
    )

    assert result.status == "blocked"
    assert "duplicate" in result.error_message.lower()
    assert launch_path_called == []

    state_path = (
        tmp_path
        / "gaming"
        / "sessions"
        / f"kc-gaming-{session_id}.json"
    )

    assert not state_path.exists()


def test_session_without_display_policy_remains_backward_compatible(
    tmp_path,
    monkeypatch,
):
    from uuid import uuid4
    from khan_agent import gaming_runtime

    _good_session_environment(monkeypatch)

    monkeypatch.setattr(
        gaming_runtime,
        "prepare_game_launch",
        lambda payload: None,
    )

    session_id = uuid4()

    result = execute_node_job(
        _session_job(
            session_id,
            display_policy_marker=False,
        ),
        gaming_state_root=tmp_path / "gaming",
        gaming_vdd_template_path=(
            tmp_path / "does-not-need-to-exist.xml"
        ),
        gaming_vdd_target_root=tmp_path / "programdata",
        **COMMON,
    )

    assert result.status == "succeeded"
    assert "display_policy" not in result.result

    state_path = (
        tmp_path
        / "gaming"
        / "sessions"
        / f"kc-gaming-{session_id}.json"
    )

    saved = json.loads(
        state_path.read_text(encoding="utf-8")
    )

    assert "display_policy" not in saved
    assert "display_policy_request" not in saved


def test_idempotent_create_with_same_policy_does_not_reapply(
    tmp_path,
    monkeypatch,
):
    from uuid import uuid4
    from khan_agent import gaming_runtime

    _good_session_environment(monkeypatch)

    monkeypatch.setattr(
        gaming_runtime,
        "prepare_game_launch",
        lambda payload: None,
    )

    template = _template(tmp_path / "template.xml")
    target = tmp_path / "programdata"

    session_id = uuid4()
    job = _session_job(session_id)

    first = execute_node_job(
        job,
        gaming_state_root=tmp_path / "gaming",
        gaming_vdd_template_path=template,
        gaming_vdd_target_root=target,
        **COMMON,
    )

    assert first.status == "succeeded"

    monkeypatch.setattr(
        gaming_runtime,
        "apply_display_policy",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError(
                "idempotent create must not reapply policy"
            )
        ),
    )

    second = execute_node_job(
        job,
        gaming_state_root=tmp_path / "gaming",
        gaming_vdd_template_path=template,
        gaming_vdd_target_root=target,
        **COMMON,
    )

    assert second.status == "succeeded"
    assert second.result["idempotent"] is True
    assert (
        second.result["display_policy"]["policy_version"]
        == "scheduler-policy-1"
    )


def test_idempotent_create_rejects_display_policy_reassignment(
    tmp_path,
    monkeypatch,
):
    from uuid import uuid4
    from khan_agent import gaming_runtime

    _good_session_environment(monkeypatch)

    monkeypatch.setattr(
        gaming_runtime,
        "prepare_game_launch",
        lambda payload: None,
    )

    template = _template(tmp_path / "template.xml")
    target = tmp_path / "programdata"

    session_id = uuid4()

    first_job = _session_job(session_id)

    first = execute_node_job(
        first_job,
        gaming_state_root=tmp_path / "gaming",
        gaming_vdd_template_path=template,
        gaming_vdd_target_root=target,
        **COMMON,
    )

    assert first.status == "succeeded"

    changed = _session_job(session_id)

    changed["payload"]["display_policy"][
        "policy_version"
    ] = "scheduler-policy-2"

    changed_result = execute_node_job(
        changed,
        gaming_state_root=tmp_path / "gaming",
        gaming_vdd_template_path=template,
        gaming_vdd_target_root=target,
        **COMMON,
    )

    assert changed_result.status == "blocked"
    assert (
        "different display policy"
        in changed_result.error_message.lower()
    )


def test_policy_bound_session_replay_cannot_silently_drop_policy(
    tmp_path,
    monkeypatch,
):
    from uuid import uuid4
    from khan_agent import gaming_runtime

    _good_session_environment(monkeypatch)

    monkeypatch.setattr(
        gaming_runtime,
        "prepare_game_launch",
        lambda payload: None,
    )

    template = _template(tmp_path / "template.xml")
    target = tmp_path / "programdata"

    session_id = uuid4()

    created = execute_node_job(
        _session_job(session_id),
        gaming_state_root=tmp_path / "gaming",
        gaming_vdd_template_path=template,
        gaming_vdd_target_root=target,
        **COMMON,
    )

    assert created.status == "succeeded"

    replay = execute_node_job(
        _session_job(
            session_id,
            display_policy_marker=False,
        ),
        gaming_state_root=tmp_path / "gaming",
        gaming_vdd_template_path=template,
        gaming_vdd_target_root=target,
        **COMMON,
    )

    assert replay.status == "blocked"
    assert (
        "must include the same display_policy"
        in replay.error_message
    )


def test_policy_transaction_restores_existing_files_on_state_commit_failure(
    tmp_path,
    monkeypatch,
):
    from khan_agent import vdd_runtime_policy

    template = _template(
        tmp_path / "template.xml"
    )

    target = tmp_path / "programdata"
    target.mkdir()

    settings = (
        target
        / "khan-vdd-settings.xml"
    )

    state = (
        target
        / vdd_runtime_policy.STATE_NAME
    )

    lkg = (
        target
        / vdd_runtime_policy.LKG_NAME
    )

    old_settings = b"OLD-SETTINGS"
    old_state = b'{"old":"state"}'
    old_lkg = b"OLD-LKG"

    settings.write_bytes(old_settings)
    state.write_bytes(old_state)
    lkg.write_bytes(old_lkg)

    real_replace = (
        vdd_runtime_policy.os.replace
    )

    def fail_state_replace(
        source,
        destination,
    ):
        destination = Path(destination)

        if (
            destination.name
            == vdd_runtime_policy.STATE_NAME
        ):
            raise OSError(
                "simulated state write failure"
            )

        return real_replace(
            source,
            destination,
        )

    monkeypatch.setattr(
        vdd_runtime_policy.os,
        "replace",
        fail_state_replace,
    )

    with pytest.raises(OSError):
        vdd_runtime_policy.apply_display_policy(
            _policy(),
            template_path=template,
            target_root=target,
        )

    assert settings.read_bytes() == old_settings
    assert state.read_bytes() == old_state
    assert lkg.read_bytes() == old_lkg


def test_first_policy_transaction_removes_partial_files_on_failure(
    tmp_path,
    monkeypatch,
):
    from khan_agent import vdd_runtime_policy

    template = _template(
        tmp_path / "template.xml"
    )

    target = tmp_path / "programdata"

    settings = (
        target
        / "khan-vdd-settings.xml"
    )

    state = (
        target
        / vdd_runtime_policy.STATE_NAME
    )

    lkg = (
        target
        / vdd_runtime_policy.LKG_NAME
    )

    real_replace = (
        vdd_runtime_policy.os.replace
    )

    def fail_state_replace(
        source,
        destination,
    ):
        destination = Path(destination)

        if (
            destination.name
            == vdd_runtime_policy.STATE_NAME
        ):
            raise OSError(
                "simulated first-apply failure"
            )

        return real_replace(
            source,
            destination,
        )

    monkeypatch.setattr(
        vdd_runtime_policy.os,
        "replace",
        fail_state_replace,
    )

    with pytest.raises(OSError):
        vdd_runtime_policy.apply_display_policy(
            _policy(),
            template_path=template,
            target_root=target,
        )

    assert not settings.exists()
    assert not state.exists()
    assert not lkg.exists()


def test_successful_transaction_keeps_normal_policy_behavior(
    tmp_path,
):
    from khan_agent import vdd_runtime_policy

    template = _template(
        tmp_path / "template.xml"
    )

    target = tmp_path / "programdata"

    result = (
        vdd_runtime_policy.apply_display_policy(
            _policy(),
            template_path=template,
            target_root=target,
        )
    )

    settings = (
        target
        / "khan-vdd-settings.xml"
    )

    state = (
        target
        / vdd_runtime_policy.STATE_NAME
    )

    assert settings.exists()
    assert state.exists()

    saved = json.loads(
        state.read_text(
            encoding="utf-8"
        )
    )

    assert isinstance(saved, dict)
    assert result["mode_count"] == 14


def _ordered_policy(
    *,
    policy_id="gaming-session:test-session",
    revision=1,
):
    payload = _policy()
    payload["policy_id"] = policy_id
    payload["revision"] = revision
    return payload


def test_runtime_policy_persists_ordering_ledger(
    tmp_path,
):
    from khan_agent import vdd_runtime_policy

    template = _template(
        tmp_path / "template.xml"
    )

    target = tmp_path / "programdata"

    result = (
        vdd_runtime_policy.apply_display_policy(
            _ordered_policy(
                revision=1,
            ),
            template_path=template,
            target_root=target,
        )
    )

    assert (
        result["policy_id"]
        == "gaming-session:test-session"
    )
    assert result["revision"] == 1
    assert len(
        result["policy_fingerprint"]
    ) == 64

    state = json.loads(
        (
            target
            / vdd_runtime_policy.STATE_NAME
        ).read_text(
            encoding="utf-8"
        )
    )

    assert state["revision"] == 1
    assert (
        state["policy_id"]
        == "gaming-session:test-session"
    )
    assert (
        state["policy_fingerprint"]
        == result["policy_fingerprint"]
    )


def test_same_revision_same_content_is_idempotent_without_render(
    tmp_path,
    monkeypatch,
):
    from khan_agent import vdd_runtime_policy

    template = _template(
        tmp_path / "template.xml"
    )
    target = tmp_path / "programdata"

    payload = _ordered_policy(
        revision=5,
    )

    first = (
        vdd_runtime_policy.apply_display_policy(
            payload,
            template_path=template,
            target_root=target,
        )
    )

    settings_before = (
        target
        / vdd_runtime_policy.TARGET_NAME
    ).read_bytes()

    def must_not_render(*args, **kwargs):
        raise AssertionError(
            "idempotent replay must not render settings"
        )

    monkeypatch.setattr(
        vdd_runtime_policy,
        "render_settings_xml",
        must_not_render,
    )

    second = (
        vdd_runtime_policy.apply_display_policy(
            payload,
            template_path=template,
            target_root=target,
        )
    )

    assert second["idempotent"] is True
    assert second["revision"] == 5
    assert (
        second["policy_fingerprint"]
        == first["policy_fingerprint"]
    )

    assert (
        target
        / vdd_runtime_policy.TARGET_NAME
    ).read_bytes() == settings_before


def test_same_revision_different_content_is_rejected(
    tmp_path,
):
    from khan_agent import vdd_runtime_policy

    template = _template(
        tmp_path / "template.xml"
    )
    target = tmp_path / "programdata"

    first = _ordered_policy(
        revision=8,
    )

    vdd_runtime_policy.apply_display_policy(
        first,
        template_path=template,
        target_root=target,
    )

    conflicting = _ordered_policy(
        revision=8,
    )

    conflicting["preferred_mode"] = {
        "width": 1280,
        "height": 720,
        "refresh_hz": 60,
    }

    with pytest.raises(
        vdd_runtime_policy.VddRuntimePolicyError,
        match="Conflicting",
    ):
        vdd_runtime_policy.apply_display_policy(
            conflicting,
            template_path=template,
            target_root=target,
        )


def test_lower_revision_is_rejected_as_stale(
    tmp_path,
):
    from khan_agent import vdd_runtime_policy

    template = _template(
        tmp_path / "template.xml"
    )
    target = tmp_path / "programdata"

    vdd_runtime_policy.apply_display_policy(
        _ordered_policy(
            revision=12,
        ),
        template_path=template,
        target_root=target,
    )

    with pytest.raises(
        vdd_runtime_policy.VddRuntimePolicyError,
        match="Stale",
    ):
        vdd_runtime_policy.apply_display_policy(
            _ordered_policy(
                revision=11,
            ),
            template_path=template,
            target_root=target,
        )


def test_higher_revision_transactionally_advances_ledger(
    tmp_path,
):
    from khan_agent import vdd_runtime_policy

    template = _template(
        tmp_path / "template.xml"
    )
    target = tmp_path / "programdata"

    first = _ordered_policy(
        revision=20,
    )

    first_result = (
        vdd_runtime_policy.apply_display_policy(
            first,
            template_path=template,
            target_root=target,
        )
    )

    second = _ordered_policy(
        revision=21,
    )

    second["policy_version"] = (
        "scheduler-policy-revision-21"
    )

    result = (
        vdd_runtime_policy.apply_display_policy(
            second,
            template_path=template,
            target_root=target,
        )
    )

    assert result["revision"] == 21
    assert (
        result["policy_fingerprint"]
        != first_result["policy_fingerprint"]
    )

    state = json.loads(
        (
            target
            / vdd_runtime_policy.STATE_NAME
        ).read_text(
            encoding="utf-8"
        )
    )

    assert state["revision"] == 21


def test_different_policy_stream_can_start_at_revision_one(
    tmp_path,
):
    from khan_agent import vdd_runtime_policy

    template = _template(
        tmp_path / "template.xml"
    )
    target = tmp_path / "programdata"

    vdd_runtime_policy.apply_display_policy(
        _ordered_policy(
            policy_id="gaming-session:first",
            revision=9,
        ),
        template_path=template,
        target_root=target,
    )

    result = (
        vdd_runtime_policy.apply_display_policy(
            _ordered_policy(
                policy_id="gaming-session:second",
                revision=1,
            ),
            template_path=template,
            target_root=target,
        )
    )

    assert (
        result["policy_id"]
        == "gaming-session:second"
    )
    assert result["revision"] == 1


def test_corrupt_runtime_policy_state_fails_closed(
    tmp_path,
):
    from khan_agent import vdd_runtime_policy

    template = _template(
        tmp_path / "template.xml"
    )
    target = tmp_path / "programdata"
    target.mkdir()

    (
        target
        / vdd_runtime_policy.STATE_NAME
    ).write_text(
        "{not-json",
        encoding="utf-8",
    )

    with pytest.raises(
        vdd_runtime_policy.VddRuntimePolicyError,
        match="unreadable",
    ):
        vdd_runtime_policy.apply_display_policy(
            _ordered_policy(),
            template_path=template,
            target_root=target,
        )


def test_revision_must_be_positive_integer():
    from khan_agent import vdd_runtime_policy

    zero = _ordered_policy(
        revision=0,
    )

    with pytest.raises(
        vdd_runtime_policy.VddRuntimePolicyError,
        match="positive integer",
    ):
        vdd_runtime_policy.policy_from_payload(
            zero
        )


def test_unordered_legacy_policy_can_change_content_without_revision(
    tmp_path,
):
    from khan_agent import vdd_runtime_policy

    template = _template(
        tmp_path / "template.xml"
    )
    target = tmp_path / "programdata"

    first = _policy()

    first.pop("policy_id", None)
    first.pop("revision", None)

    vdd_runtime_policy.apply_display_policy(
        first,
        template_path=template,
        target_root=target,
    )

    second = _policy()
    second.pop("policy_id", None)
    second.pop("revision", None)

    second["policy_version"] = (
        "legacy-unordered-second"
    )

    result = (
        vdd_runtime_policy.apply_display_policy(
            second,
            template_path=template,
            target_root=target,
        )
    )

    assert (
        result["policy_version"]
        == "legacy-unordered-second"
    )


def test_policy_id_and_revision_must_be_supplied_together():
    from khan_agent import vdd_runtime_policy

    only_id = _policy()
    only_id["policy_id"] = "stream:test"
    only_id.pop("revision", None)

    with pytest.raises(
        vdd_runtime_policy.VddRuntimePolicyError,
        match="supplied together",
    ):
        vdd_runtime_policy.policy_from_payload(
            only_id
        )

    only_revision = _policy()
    only_revision["revision"] = 2
    only_revision.pop("policy_id", None)

    with pytest.raises(
        vdd_runtime_policy.VddRuntimePolicyError,
        match="supplied together",
    ):
        vdd_runtime_policy.policy_from_payload(
            only_revision
        )


def test_session_policy_new_apply_triggers_live_activation(
    tmp_path,
    monkeypatch,
):
    from khan_agent import gaming_runtime

    monkeypatch.setattr(
        gaming_runtime,
        "live_activation_available",
        lambda: True,
    )

    calls = {
        "apply": 0,
        "activate": 0,
    }

    def fake_apply(
        payload,
        *,
        template_path,
        target_root,
    ):
        calls["apply"] += 1

        return {
            "policy_version": "test-v1",
            "policy_id": "gaming-session:test",
            "revision": 1,
            "settings_path": str(
                target_root
                / "khan-vdd-settings.xml"
            ),
        }

    def fake_activate():
        calls["activate"] += 1

        return {
            "activation_required": True,
            "activation_method":
                "pnputil-restart-device",
            "instance_id":
                r"ROOT\DISPLAY\0000",
            "healthy": True,
            "reboot_required": False,
        }

    monkeypatch.setattr(
        gaming_runtime,
        "apply_display_policy",
        fake_apply,
    )

    monkeypatch.setattr(
        gaming_runtime,
        "activate_vdd_policy",
        fake_activate,
    )

    result = (
        gaming_runtime
        ._apply_session_display_policy(
            {
                "policy_version": "test-v1",
            },
            template_path=(
                tmp_path / "template.xml"
            ),
            target_root=tmp_path,
        )
    )

    assert calls["apply"] == 1
    assert calls["activate"] == 1

    assert (
        result["activation"]
        ["activation_method"]
        == "pnputil-restart-device"
    )

    assert (
        result["activation"]
        ["reboot_required"]
        is False
    )


def test_session_policy_idempotent_replay_skips_live_activation(
    tmp_path,
    monkeypatch,
):
    from khan_agent import gaming_runtime

    def fake_apply(
        payload,
        *,
        template_path,
        target_root,
    ):
        return {
            "policy_version": "test-v1",
            "policy_id": "gaming-session:test",
            "revision": 7,
            "idempotent": True,
        }

    def forbidden_activation():
        raise AssertionError(
            "idempotent policy replay must "
            "not restart VDD"
        )

    monkeypatch.setattr(
        gaming_runtime,
        "apply_display_policy",
        fake_apply,
    )

    monkeypatch.setattr(
        gaming_runtime,
        "activate_vdd_policy",
        forbidden_activation,
    )

    result = (
        gaming_runtime
        ._apply_session_display_policy(
            {
                "policy_version": "test-v1",
            },
            template_path=(
                tmp_path / "template.xml"
            ),
            target_root=tmp_path,
        )
    )

    assert result["idempotent"] is True

    assert (
        result["activation"]
        ["activation_required"]
        is False
    )

    assert (
        result["activation"]["reason"]
        == "idempotent-policy-replay"
    )


def test_session_policy_activation_failure_fails_session_create_path(
    tmp_path,
    monkeypatch,
):
    from khan_agent import (
        gaming_runtime,
        vdd_activation,
    )

    monkeypatch.setattr(
        gaming_runtime,
        "live_activation_available",
        lambda: True,
    )

    def fake_apply(
        payload,
        *,
        template_path,
        target_root,
    ):
        return {
            "policy_version": "test-v2",
            "policy_id": "gaming-session:test",
            "revision": 2,
        }

    def fail_activation():
        raise (
            vdd_activation
            .VddActivationError(
                "simulated VDD activation failure"
            )
        )

    monkeypatch.setattr(
        gaming_runtime,
        "apply_display_policy",
        fake_apply,
    )

    monkeypatch.setattr(
        gaming_runtime,
        "activate_vdd_policy",
        fail_activation,
    )

    with pytest.raises(
        gaming_runtime.GamingRuntimeError,
        match=(
            "policy persisted but live "
            "activation failed"
        ),
    ):
        (
            gaming_runtime
            ._apply_session_display_policy(
                {
                    "policy_version":
                        "test-v2",
                },
                template_path=(
                    tmp_path / "template.xml"
                ),
                target_root=tmp_path,
            )
        )


def test_session_policy_non_windows_persists_without_pnp_activation(
    tmp_path,
    monkeypatch,
):
    from khan_agent import gaming_runtime

    calls = {
        "apply": 0,
        "activate": 0,
    }

    def fake_apply(
        payload,
        *,
        template_path,
        target_root,
    ):
        calls["apply"] += 1
        return {
            "policy_version": "test-linux-ci",
            "policy_id": "gaming-session:test",
            "revision": 1,
        }

    def forbidden_activation():
        calls["activate"] += 1
        raise AssertionError(
            "non-Windows host must not execute Windows PnP"
        )

    monkeypatch.setattr(
        gaming_runtime,
        "apply_display_policy",
        fake_apply,
    )

    monkeypatch.setattr(
        gaming_runtime,
        "live_activation_available",
        lambda: False,
    )

    monkeypatch.setattr(
        gaming_runtime,
        "activate_vdd_policy",
        forbidden_activation,
    )

    result = (
        gaming_runtime
        ._apply_session_display_policy(
            {
                "policy_version": "test-linux-ci",
            },
            template_path=(
                tmp_path / "template.xml"
            ),
            target_root=tmp_path,
        )
    )

    assert calls["apply"] == 1
    assert calls["activate"] == 0

    activation = result["activation"]

    assert (
        activation["activation_required"]
        is False
    )

    assert (
        activation["activation_available"]
        is False
    )

    assert (
        activation["reason"]
        == "windows-live-activation-unavailable"
    )

    assert (
        activation["reboot_required"]
        is False
    )
