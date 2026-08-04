from app.security.jwt import create_access_token, decode_access_token
from app.security.password import hash_password, verify_password


def test_password_hashing() -> None:
    value = "A-Strong-Test-Password-123"
    password_hash = hash_password(value)
    assert password_hash != value
    assert verify_password(value, password_hash)
    assert not verify_password("wrong-password", password_hash)


def test_access_token_round_trip() -> None:
    subject = "00000000-0000-0000-0000-000000000001"
    payload = decode_access_token(create_access_token(subject))
    assert payload is not None
    assert payload["sub"] == subject
