from pathlib import Path


def test_portal_renders_public_endpoint_lifecycle():
    root = Path(__file__).resolve().parents[2]
    js = (root / "customer-portal" / "portal.js").read_text()

    assert "public_endpoints" in js
    assert "Public endpoints" in js
    assert "private_port" in js
    assert "display_status" in js


def test_portal_ssh_requires_active_public_mapping():
    root = Path(__file__).resolve().parents[2]
    js = (root / "customer-portal" / "portal.js").read_text()

    assert 'e.protocol==="tcp"' in js
    assert "Number(e.private_port)===22" in js
    assert 'e.status==="active"' in js
    assert "-p ${ssh.public_port}" in js


def test_portal_does_not_build_ssh_from_private_ip():
    root = Path(__file__).resolve().parents[2]
    js = (root / "customer-portal" / "portal.js").read_text()

    assert (
        "ssh ${esc(v.access_username)}@${esc(v.primary_ip)}"
        not in js
    )


def test_portal_explains_endpoint_configuration():
    root = Path(__file__).resolve().parents[2]
    js = (root / "customer-portal" / "portal.js").read_text()

    assert "SSH endpoint is being configured." in js
