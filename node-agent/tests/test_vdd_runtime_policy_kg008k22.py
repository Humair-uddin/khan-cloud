from __future__ import annotations

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
