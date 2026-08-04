#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo."
  exit 1
fi

AGENT_ROOT="${1:-/opt/khan-cloud/source/node-agent}"
mkdir -p /etc/khan-cloud-agent /var/lib/khan-cloud-agent

if [ ! -f /etc/khan-cloud-agent/config.yaml ]; then
  cp "$AGENT_ROOT/config.example.yaml" /etc/khan-cloud-agent/config.yaml
  chmod 600 /etc/khan-cloud-agent/config.yaml
fi

install -m 0644 "$AGENT_ROOT/systemd/khan-cloud-agent.service" \
  /etc/systemd/system/khan-cloud-agent.service

systemctl daemon-reload

echo "Service installed but NOT enabled or started."
echo "Review /etc/khan-cloud-agent/config.yaml first."
echo "Then run:"
echo "  sudo systemctl enable --now khan-cloud-agent"
