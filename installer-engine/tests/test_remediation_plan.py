from kc_installer.models import Manifest
from kc_installer.preflight import build_remediation_plan


def test_remediation_plan_contains_only_approved_missing_dependency() -> None:
    manifest = Manifest.model_validate(
        {
            "feature_pack": {
                "id": "FP-REMEDIATE",
                "name": "Remediation Test",
                "version": "1.0.0",
            },
            "components": {},
            "operations": {
                "require_clean_git": False,
            },
            "preflight": {
                "dependencies": [
                    {
                        "name": "Docker",
                        "command": "kc-command-does-not-exist",
                        "classification": "remediable",
                        "remediation": {
                            "type": "command",
                            "command": [
                                "apt-get",
                                "install",
                                "-y",
                                "docker.io",
                            ],
                            "description": "Install Docker from approved repository.",
                        },
                    },
                    {
                        "name": "Manual Dependency",
                        "command": "another-missing-command",
                        "classification": "manual",
                    },
                ]
            },
        }
    )

    plan = build_remediation_plan(manifest)

    assert len(plan) == 1
    assert plan[0].dependency_name == "Docker"
    assert plan[0].action_type == "command"
    assert plan[0].command == [
        "apt-get",
        "install",
        "-y",
        "docker.io",
    ]


def test_remediable_dependency_without_action_is_not_in_plan() -> None:
    manifest = Manifest.model_validate(
        {
            "feature_pack": {
                "id": "FP-REMEDIATE",
                "name": "Remediation Test",
                "version": "1.0.0",
            },
            "components": {},
            "operations": {
                "require_clean_git": False,
            },
            "preflight": {
                "dependencies": [
                    {
                        "name": "Missing",
                        "command": "kc-command-does-not-exist",
                        "classification": "remediable",
                    }
                ]
            },
        }
    )

    assert build_remediation_plan(manifest) == []
