from khan_agent.identity import hardware_fingerprint, IdentityStore

def test_fingerprint_is_stable_and_uses_hardware_evidence():
    e={"system_uuid":"ABC","serial_number":"SER123","manufacturer":"Dell Inc.","model":"PowerEdge R7425"}
    assert hardware_fingerprint(e)==hardware_fingerprint(dict(e))
    assert len(hardware_fingerprint(e))==64

def test_fingerprint_requires_uuid_or_serial():
    assert hardware_fingerprint({"manufacturer":"Dell","model":"R7425"})==""

def test_old_identity_is_upgraded_without_changing_node_uuid(tmp_path, monkeypatch):
    (tmp_path/'identity.json').write_text('{"node_uuid":"old-id","hostname":"h","platform":"windows","platform_release":"11","machine":"AMD64"}')
    monkeypatch.setattr('khan_agent.identity.collect_hardware_identity', lambda:{"system_uuid":"U","serial_number":"S","manufacturer":"Dell","model":"R7425"})
    x=IdentityStore(tmp_path).load_or_create()
    assert x.node_uuid=='old-id'
    assert x.hardware_fingerprint
