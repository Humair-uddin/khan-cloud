#!/usr/bin/env bash
set -euo pipefail
if [[ "$(id -u)" -ne 0 ]]; then echo "Run with sudo."; exit 1; fi
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME=/opt/khan-cloud/runtime/node-agent
BACKUP="/tmp/khan-cloud-secure-vps-agent-backup-$(date +%Y%m%d-%H%M%S).tar.gz"

echo "===== KHAN CLOUD SECURE VPS AGENT UPDATE ====="
test -f /var/lib/khan-cloud-agent/credentials.json
systemctl is-active --quiet libvirtd
virsh -c qemu:///system net-info kc-vps-net >/dev/null

tar -czf "$BACKUP" "$RUNTIME/khan_agent" 2>/dev/null || true
systemctl stop khan-cloud-agent
cp -a "$HERE/khan_agent/." "$RUNTIME/khan_agent/"
chown -R root:root "$RUNTIME/khan_agent"
chmod -R go-w "$RUNTIME/khan_agent"
"$RUNTIME/.venv/bin/python" -m compileall -q "$RUNTIME/khan_agent"
systemctl start khan-cloud-agent

echo "===== HEARTBEAT STABILITY ====="
sleep 25
systemctl is-active --quiet khan-cloud-agent
restarts="$(systemctl show khan-cloud-agent -p NRestarts --value)"
echo "NRestarts=$restarts"

echo "===== HYPERVISOR ====="
runuser -u khan-cloud-agent -- virsh -c qemu:///system list --all

echo
echo "SUCCESS: SECURE VPS AGENT UPDATE APPLIED"
echo "Backup: $BACKUP"
