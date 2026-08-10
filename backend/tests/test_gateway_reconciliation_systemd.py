from pathlib import Path


def test_gateway_reconciliation_systemd_units_exist():
    root = Path(__file__).resolve().parents[1]

    service = (
        root
        / "deploy"
        / "systemd"
        / "khan-cloud-gateway-reconcile.service"
    )

    timer = (
        root
        / "deploy"
        / "systemd"
        / "khan-cloud-gateway-reconcile.timer"
    )

    assert service.is_file()
    assert timer.is_file()


def test_gateway_reconciliation_service_is_oneshot():
    root = Path(__file__).resolve().parents[1]

    text = (
        root
        / "deploy"
        / "systemd"
        / "khan-cloud-gateway-reconcile.service"
    ).read_text()

    assert "Type=oneshot" in text
    assert "User=khanadmin" in text
    assert "Group=khanadmin" in text

    assert (
        "python -m app.cli.reconcile_gateway --limit 100"
        in text
    )

    assert "SuccessExitStatus=0 2" in text


def test_gateway_reconciliation_timer_is_periodic():
    root = Path(__file__).resolve().parents[1]

    text = (
        root
        / "deploy"
        / "systemd"
        / "khan-cloud-gateway-reconcile.timer"
    ).read_text()

    assert "OnBootSec=45s" in text
    assert "OnUnitActiveSec=30s" in text
    assert "Persistent=true" in text
