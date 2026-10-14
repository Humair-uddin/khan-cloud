from __future__ import annotations

from collections.abc import Iterator

import pytest


@pytest.fixture(autouse=True)
def deployment_safe_runtime_guard(
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[frozenset[str]]:
    """Fail closed if a deployment-safe test reaches a mutation boundary."""
    if request.node.get_closest_marker(
        "deployment_safe"
    ) is None:
        yield frozenset()
        return

    from khan_agent import gaming_launchers
    from khan_agent import gaming_runtime
    from khan_agent import runtime_ownership
    from khan_agent import vdd_activation
    from khan_agent import vdd_runtime_policy
    from khan_agent import windows_interactive
    from khan_agent import windows_presentation

    guarded = (
        (
            gaming_runtime,
            "_establish_presentation_contract",
        ),
        (gaming_runtime, "_apply_session_display_policy"),
        (gaming_runtime, "prepare_game_launch"),
        (gaming_runtime, "launch_prepared_game"),
        (gaming_runtime, "activate_vdd_policy"),
        (gaming_runtime, "_cleanup_failed_launch"),
        (gaming_launchers, "prepare_game_launch"),
        (gaming_launchers, "launch_prepared_game"),
        (
            windows_presentation,
            "establish_vdd_presentation_contract",
        ),
        (windows_presentation, "ensure_game_on_vdd"),
        (windows_interactive, "launch_in_active_session"),
        (vdd_activation, "restart_vdd_device"),
        (vdd_activation, "activate_vdd_policy"),
        (vdd_runtime_policy, "apply_display_policy"),
        (vdd_runtime_policy, "restore_last_known_good"),
        (
            runtime_ownership,
            "terminate_runtime_ownership",
        ),
    )

    guarded_names = frozenset(
        f"{module.__name__}.{attribute}"
        for module, attribute in guarded
    )

    for module, attribute in guarded:
        qualified_name = (
            f"{module.__name__}.{attribute}"
        )

        def blocked(
            *_args,
            _qualified_name=qualified_name,
            **_kwargs,
        ):
            raise AssertionError(
                "deployment_safe test reached protected "
                f"runtime boundary: {_qualified_name}"
            )

        blocked._khan_deployment_safe_guard = True
        monkeypatch.setattr(module, attribute, blocked)

    yield guarded_names
