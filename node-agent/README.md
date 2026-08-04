# Khan Cloud Universal Agent v0.6.0

This is the first working Universal Agent framework.

## Implemented

- YAML configuration
- Persistent node identity
- Agent state machine
- Structured startup and heartbeat logs
- Optional heartbeat client
- Read-only plugin loader skeleton
- Linux systemd unit
- Unit tests
- Observation-only safe default

## Safety boundary

This release does not:

- install or upgrade GPU drivers;
- change BIOS, firmware, Secure Boot, RAID, partitions, or networking;
- delete host or customer files;
- execute AI recommendations;
- stop workloads;
- enable itself automatically.

## Developer verification

```bash
cd node-agent
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest -q
.venv/bin/python -m khan_agent --once
```

## Linux service installation

```bash
sudo ./scripts/install-linux-service.sh /opt/khan-cloud/source/node-agent
```

The script installs the unit but deliberately does not enable or start it.
Review `/etc/khan-cloud-agent/config.yaml` first.

## Heartbeat

Heartbeat is disabled by default because the exact control-plane heartbeat
contract must be verified before the service is activated.

After the backend heartbeat endpoint and schema are confirmed, set:

```yaml
heartbeat:
  enabled: true
  endpoint: /api/v1/nodes/heartbeat
```
