from __future__ import annotations

from pathlib import Path

from kc_installer.backend_runtime import BackendRuntimeError
from kc_installer.runtime_switch import current_runtime, switch_runtime
from kc_installer.state import InstallerState


def activate_transaction_runtime(
    *,
    state: InstallerState,
    transaction_id: str,
    runtime_root: Path,
    active_link: Path,
    candidate: Path,
    requirements_sha256: str,
) -> None:
    previous = current_runtime(runtime_root, active_link)

    state.record_backend_runtime_intent(
        transaction_id,
        runtime_root=runtime_root,
        active_link=active_link,
        previous_path=previous,
        candidate_path=candidate,
        requirements_sha256=requirements_sha256,
    )

    switch_runtime(
        runtime_root=runtime_root,
        active_link=active_link,
        expected=previous,
        replacement=candidate,
    )

    state.transition_backend_runtime(
        transaction_id,
        expected_phase="intent",
        new_phase="activated",
    )


def recover_transaction_runtime(
    *,
    state: InstallerState,
    transaction_id: str,
) -> str:
    record = state.backend_runtime_record(transaction_id)

    if record is None:
        raise BackendRuntimeError(
            "No runtime transaction record exists."
        )

    phase = record["phase"]

    if phase in {"restored", "committed"}:
        return phase

    root = Path(record["runtime_root"])
    link = Path(record["active_link"])
    candidate = Path(record["candidate_path"])

    previous = (
        Path(record["previous_path"])
        if record["previous_path"]
        else None
    )

    observed = current_runtime(root, link)

    if observed == candidate.resolve(strict=True):
        switch_runtime(
            runtime_root=root,
            active_link=link,
            expected=candidate,
            replacement=previous,
        )
    elif observed != (
        previous.resolve(strict=True)
        if previous is not None
        else None
    ):
        raise BackendRuntimeError(
            "Recovery refused: runtime ownership conflict."
        )

    state.transition_backend_runtime(
        transaction_id,
        expected_phase=phase,
        new_phase="restored",
    )

    return "restored"
