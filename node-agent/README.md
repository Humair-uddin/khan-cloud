# Khan Cloud Universal Agent v0.6.3

## FP-009 capability

The agent can now:

- enroll through the existing `POST /api/v1/nodes/register` endpoint;
- store the returned node ID and secret with mode `0600`;
- send an authenticated heartbeat through `POST /api/v1/nodes/heartbeat`;
- refuse heartbeat when enrollment credentials are missing;
- avoid printing the node secret in logs.

## Safe test flow

Create a private configuration:

```bash
cp config.example.yaml /home/khanadmin/khan-agent-test.yaml
chmod 600 /home/khanadmin/khan-agent-test.yaml
```

Edit only the enrollment token and node name.

Enroll:

```bash
.venv/bin/python -m khan_agent \
  --config /home/khanadmin/khan-agent-test.yaml \
  --enroll
```

Send one heartbeat:

```bash
.venv/bin/python -m khan_agent \
  --config /home/khanadmin/khan-agent-test.yaml \
  --heartbeat-once
```

Credentials are stored under the configured `state_directory`.

## Current limitation

This early enrollment model uses a shared enrollment token and a generated node
secret. Future secure enrollment will replace it with short-lived, scoped tokens
and certificate-based identity.
