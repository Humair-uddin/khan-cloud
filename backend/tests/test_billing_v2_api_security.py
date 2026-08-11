from pathlib import Path


def _api_source() -> str:
    root = Path(__file__).resolve().parents[1]
    return (
        root
        / "app"
        / "api"
        / "v1"
        / "commercial.py"
    ).read_text()


def test_private_commercial_helpers_are_explicitly_imported():
    source = _api_source()

    assert "_can_manage_commerce," in source
    assert "_org," in source


def test_manual_wallet_topup_is_operator_only():
    source = _api_source()

    assert '@router.post("/operator/wallets/top-up"' in source

    marker = 'def billing_wallet_topup('
    start = source.index(marker)
    section = source[start:start + 500]

    assert 'require_permission("commerce.manage")' in section


def test_customer_cannot_directly_credit_wallet_endpoint():
    source = _api_source()

    assert '@router.post("/wallets/top-up"' not in source
