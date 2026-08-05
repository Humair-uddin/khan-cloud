from khan_agent.credentials import CredentialStore, NodeCredentials


def test_credentials_are_persisted_with_private_permissions(tmp_path) -> None:
    store = CredentialStore(tmp_path)
    credentials = NodeCredentials(node_id="node-1", node_secret="secret")
    store.save(credentials)

    loaded = store.load()
    assert loaded == credentials
    assert (store.path.stat().st_mode & 0o777) == 0o600
