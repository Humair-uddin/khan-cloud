from pathlib import Path

from khan_agent import cli


def test_linux_default_config_path_remains_unchanged(monkeypatch):
    monkeypatch.setattr("platform.system", lambda: "Linux")

    parser = cli.build_parser()
    args = parser.parse_args([])

    assert Path(args.config) == Path("/etc/khan-cloud-agent/config.yaml")


def test_windows_default_config_path_uses_programdata(monkeypatch, tmp_path):
    monkeypatch.setattr("platform.system", lambda: "Windows")
    monkeypatch.setenv("ProgramData", str(tmp_path / "ProgramData"))

    parser = cli.build_parser()
    args = parser.parse_args([])

    assert Path(args.config) == (
        tmp_path / "ProgramData" / "KhanCloud" / "Agent" / "config.yaml"
    )


def test_explicit_config_path_overrides_platform_default(monkeypatch, tmp_path):
    monkeypatch.setattr("platform.system", lambda: "Windows")

    custom = tmp_path / "custom-config.yaml"

    parser = cli.build_parser()
    args = parser.parse_args(["--config", str(custom)])

    assert Path(args.config) == custom
