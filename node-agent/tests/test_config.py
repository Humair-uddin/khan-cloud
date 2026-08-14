from pathlib import Path

from khan_agent.config import AgentSettings


def test_safe_defaults_when_config_missing(tmp_path: Path) -> None:
    settings = AgentSettings.load(tmp_path / "missing.yaml")
    assert settings.agent.observation_only is True
    assert settings.heartbeat.enabled is False


def test_agent_role_defaults_to_generic(tmp_path):
    settings = AgentSettings.load(tmp_path / "missing.yaml")
    assert settings.agent.node_role == "generic"


def test_windows_default_agent_paths(monkeypatch, tmp_path):
    monkeypatch.setattr("platform.system", lambda: "Windows")
    monkeypatch.setenv("ProgramData", str(tmp_path / "ProgramData"))

    settings = AgentSettings.load(tmp_path / "missing.yaml")

    assert settings.agent.state_directory == tmp_path / "ProgramData" / "KhanCloud" / "Agent"
    assert settings.agent.plugin_directory == tmp_path / "ProgramData" / "KhanCloud" / "Agent" / "plugins"


def test_linux_default_agent_paths_remain_unchanged(monkeypatch, tmp_path):
    monkeypatch.setattr("platform.system", lambda: "Linux")

    settings = AgentSettings.load(tmp_path / "missing.yaml")

    assert settings.agent.state_directory == Path("/var/lib/khan-cloud-agent")
    assert settings.agent.plugin_directory == Path("/etc/khan-cloud-agent/plugins")
