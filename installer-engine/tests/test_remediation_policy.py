from kc_installer.models import Manifest
from kc_installer.preflight import evaluate_remediation_policy


def make_manifest(
    *,
    allow_dependency_install: bool = False,
    classification: str = "remediable",
) -> Manifest:
    return Manifest.model_validate(
        {
            "feature_pack": {
                "id": "FP-POLICY",
                "name": "Policy Test",
                "version": "1.0.0",
                # Deliberately true to prove this self-declared
                # field is NOT accepted as trust verification.
                "signed": True,
            },
            "components": {},
            "operations": {
                "allow_dependency_install": allow_dependency_install,
            },
            "preflight": {
                "dependencies": [
                    {
                        "name": "Docker",
                        "command": "kc-command-does-not-exist",
                        "classification": classification,
                        "remediation": {
                            "type": "command",
                            "command": [
                                "apt-get",
                                "install",
                                "-y",
                                "docker.io",
                            ],
                            "description": "Install Docker.",
                        },
                    }
                ]
            },
        }
    )


def test_policy_blocks_when_manifest_permission_is_disabled() -> None:
    manifest = make_manifest(
        allow_dependency_install=False,
    )

    decisions = evaluate_remediation_policy(
        manifest,
        dry_run=False,
        trusted_package=True,
    )

    assert len(decisions) == 1
    assert decisions[0].eligible is False
    assert decisions[0].reason == "dependency installation is not permitted"


def test_policy_blocks_dry_run() -> None:
    manifest = make_manifest(
        allow_dependency_install=True,
    )

    decisions = evaluate_remediation_policy(
        manifest,
        dry_run=True,
        trusted_package=True,
    )

    assert len(decisions) == 1
    assert decisions[0].eligible is False
    assert decisions[0].reason == "dry-run prohibits remediation execution"


def test_policy_blocks_untrusted_package() -> None:
    manifest = make_manifest(
        allow_dependency_install=True,
    )

    decisions = evaluate_remediation_policy(
        manifest,
        dry_run=False,
        trusted_package=False,
    )

    assert len(decisions) == 1
    assert decisions[0].eligible is False
    assert decisions[0].reason == "package trust has not been verified"


def test_manifest_signed_flag_does_not_establish_trust() -> None:
    manifest = make_manifest(
        allow_dependency_install=True,
    )

    assert manifest.feature_pack.signed is True

    decisions = evaluate_remediation_policy(
        manifest,
        dry_run=False,
    )

    assert decisions[0].eligible is False
    assert decisions[0].reason == "package trust has not been verified"


def test_policy_allows_approved_trusted_action() -> None:
    manifest = make_manifest(
        allow_dependency_install=True,
    )

    decisions = evaluate_remediation_policy(
        manifest,
        dry_run=False,
        trusted_package=True,
    )

    assert len(decisions) == 1

    decision = decisions[0]

    assert decision.dependency_name == "Docker"
    assert decision.action_type == "command"
    assert decision.command == [
        "apt-get",
        "install",
        "-y",
        "docker.io",
    ]
    assert decision.eligible is True
    assert decision.reason == "eligible"


def test_required_dependency_never_becomes_remediation_action() -> None:
    manifest = make_manifest(
        allow_dependency_install=True,
        classification="required",
    )

    decisions = evaluate_remediation_policy(
        manifest,
        dry_run=False,
        trusted_package=True,
    )

    assert decisions == []


def test_manual_dependency_never_becomes_remediation_action() -> None:
    manifest = make_manifest(
        allow_dependency_install=True,
        classification="manual",
    )

    decisions = evaluate_remediation_policy(
        manifest,
        dry_run=False,
        trusted_package=True,
    )

    assert decisions == []
