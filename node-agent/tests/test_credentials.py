import platform

from khan_agent.credentials import CredentialStore, NodeCredentials


def test_credentials_are_persisted_with_private_permissions(tmp_path) -> None:
    store = CredentialStore(tmp_path)
    credentials = NodeCredentials(node_id="node-1", node_secret="secret")
    store.save(credentials)

    loaded = store.load()
    assert loaded == credentials

    # POSIX agents protect credentials with mode 0600.
    # Windows agents use icacls instead; that contract is covered
    # independently by test_file_security.py.
    if platform.system() != "Windows":
        assert (store.path.stat().st_mode & 0o777) == 0o600


def test_load_resecures_existing_credentials_before_read(
    monkeypatch,
    tmp_path,
):
    from khan_agent import credentials as credentials_module

    path = tmp_path / "credentials.json"
    path.write_text(
        '{"node_id": "node-existing", '
        '"node_secret": "secret-existing"}'
    )

    secured = []

    def fake_secure_private_file(target):
        secured.append(target)

    monkeypatch.setattr(
        credentials_module,
        "secure_private_file",
        fake_secure_private_file,
    )

    store = CredentialStore(tmp_path)
    loaded = store.load()

    assert secured == [path]
    assert loaded.node_id == "node-existing"
    assert loaded.node_secret == "secret-existing"
