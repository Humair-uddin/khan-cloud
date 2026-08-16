from pathlib import Path
from khan_agent import gaming_inventory

def test_acf_value_parses_cs2():
    text = '"appid" "730"\n"name" "Counter-Strike 2"\n"buildid" "123"'
    assert gaming_inventory._acf_value(text, "appid") == "730"
    assert gaming_inventory._acf_value(text, "name") == "Counter-Strike 2"

def test_absent_steam_is_safe(monkeypatch):
    monkeypatch.setattr(gaming_inventory, "_steam_roots", lambda: [])
    result = gaming_inventory.collect_steam_inventory()
    assert result["installed"] is False
    assert result["games"] == []

def test_cs2_manifest_discovery(monkeypatch, tmp_path: Path):
    steam = tmp_path / "Steam"
    apps = steam / "steamapps"
    apps.mkdir(parents=True)
    (apps / "appmanifest_730.acf").write_text('"appid" "730"\n"name" "Counter-Strike 2"\n"installdir" "Counter-Strike Global Offensive"\n"buildid" "999"\n')
    monkeypatch.setattr(gaming_inventory, "_steam_roots", lambda: [steam])
    games = gaming_inventory.collect_steam_inventory()["games"]
    assert len(games) == 1
    assert games[0]["app_id"] == "730"
    assert games[0]["build_id"] == "999"
