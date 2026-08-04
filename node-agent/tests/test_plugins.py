from khan_agent.plugins import PluginManager


def test_missing_plugin_directory_is_valid(tmp_path) -> None:
    manager = PluginManager(tmp_path / "plugins")
    assert manager.load_all() == []
