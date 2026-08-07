import json
from pathlib import Path

from kc_installer.cli import main


def test_plan_cli_exposes_remediation_without_execution(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    package = tmp_path / "package"
    package.mkdir()

    target = tmp_path / "target"
    target.mkdir()

    marker = tmp_path / "must-not-exist"

    (package / "manifest.yaml").write_text(
        f"""
feature_pack:
  id: FP-PLAN
  name: Plan Test
  version: 1.0.0

components: {{}}

operations:
  require_clean_git: false

preflight:
  dependencies:
    - name: Missing Dependency
      command: kc-command-does-not-exist
      classification: remediable
      remediation:
        type: command
        command:
          - touch
          - {marker}
        description: Test-only remediation action.
"""
    )

    monkeypatch.setattr(
        "sys.argv",
        [
            "kc-installer",
            "plan",
            str(package),
            "--target",
            str(target),
        ],
    )

    main()

    output = json.loads(capsys.readouterr().out)

    assert len(output["remediation_plan"]) == 1
    assert output["remediation_plan"][0]["dependency"] == (
        "Missing Dependency"
    )

    assert output["remediation_plan"][0]["command"] == [
        "touch",
        str(marker),
    ]

    # Planning must NEVER execute remediation.
    assert not marker.exists()
