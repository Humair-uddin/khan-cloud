from khan_agent.identity import IdentityStore


def test_identity_is_persistent(tmp_path) -> None:
    store = IdentityStore(tmp_path)
    first = store.load_or_create()
    second = store.load_or_create()
    assert first.node_uuid == second.node_uuid
    assert (tmp_path / "identity.json").exists()
