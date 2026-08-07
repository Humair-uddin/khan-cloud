from pathlib import Path

from kc_installer.engine import install
from kc_installer.paths import InstallerPaths
from kc_installer.state import InstallerState


def make_paths(root: Path) -> InstallerPaths:
    return InstallerPaths(
        source_root=root / "source",
        platform_root=root,
        runtime_root=root / "runtime" / "installer",
        state_root=root / "state" / "installer",
        backup_root=root / "backups" / "feature-packs",
        package_root=root / "packages",
    )


def test_engine_persists_remediation_plan_without_execution(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()

    package = tmp_path / "package"
    package.mkdir()

    marker = tmp_path / "must-not-exist"

    (package / "manifest.yaml").write_text(
        f"""
feature_pack:
  id: FP-REMEDIATION-PERSIST
  name: Remediation Persistence Test
  version: 1.0.0

components: {{}}

operations:
  require_clean_git: false
  run_health_checks: false

preflight:
  dependencies:
    - name: Missing Dependency
      command: kc-command-does-not-exist
      classification: remediable
      description: Test dependency.
      remediation:
        type: command
        command:
          - touch
          - "{marker}"
        description: Test-only approved remediation.
"""
    )

    paths = make_paths(tmp_path / "khan-cloud")

    install(
        package,
        repository,
        dry_run=True,
        paths=paths,
    )

    assert not marker.exists()

    state = InstallerState(paths.database_path)
    transactions = state.installations()

    assert len(transactions) == 1

    transaction_id = transactions[0]["transaction_id"]
    plan = state.remediation_plan(transaction_id)

    assert plan == [
        {
            "dependency_name": "Missing Dependency",
            "action_type": "command",
            "command": [
                "touch",
                str(marker),
            ],
            "description": "Test-only approved remediation.",
            "position": 0,
            "eligible": False,
            "policy_reason": "dry-run prohibits remediation execution",
        }
    ]

    journal = state.journal(transaction_id)

    assert any(
        entry["stage"] == "remediation_plan"
        and entry["status"] == "planned"
        for entry in journal
    )



def test_engine_journals_remediation_policy_decision(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()

    package = tmp_path / "package"
    package.mkdir()

    (package / "manifest.yaml").write_text(
        """
feature_pack:
  id: FP-POLICY-JOURNAL
  name: Policy Journal Test
  version: 1.0.0

components: {}

operations:
  require_clean_git: false
  allow_dependency_install: true
  run_health_checks: false

preflight:
  dependencies:
    - name: Missing Dependency
      command: kc-command-does-not-exist
      classification: remediable
      remediation:
        type: command
        command:
          - echo
          - test
        description: Test action.
"""
    )

    paths = make_paths(tmp_path / "khan-cloud")

    install(
        package,
        repository,
        dry_run=True,
        paths=paths,
    )

    state = InstallerState(paths.database_path)
    transaction_id = state.installations()[0]["transaction_id"]

    entries = state.journal(transaction_id)

    policy_entries = [
        entry
        for entry in entries
        if entry["stage"] == "remediation_policy"
    ]

    assert len(policy_entries) == 1
    assert policy_entries[0]["status"] == "blocked"
    assert (
        policy_entries[0]["message"]
        == "Missing Dependency: dry-run prohibits remediation execution"
    )
