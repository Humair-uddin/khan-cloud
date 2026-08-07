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

Edit the deployment enrollment code and node name. The legacy shared enrollment token is retained only for backwards-compatible private/lab use.

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

Enrollment now prefers the scoped Deployment Profile enrollment code and retains the generated node
secret for authenticated heartbeats. The legacy shared token is a compatibility fallback
and certificate-based identity.
