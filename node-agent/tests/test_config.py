from pathlib import Path

from khan_agent.config import AgentSettings


def test_safe_defaults_when_config_missing(tmp_path: Path) -> None:
    settings = AgentSettings.load(tmp_path / "missing.yaml")
    assert settings.agent.observation_only is True
    assert settings.heartbeat.enabled is False
