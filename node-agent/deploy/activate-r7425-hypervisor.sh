#!/usr/bin/env bash
set -euo pipefail
if [[ "$(id -u)" -ne 0 ]]; then echo "Run with sudo."; exit 1; fi
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_PAYLOAD="$HERE/node-agent"
BACKUP="/tmp/khan-cloud-r7425-hypervisor-backup-$(date +%Y%m%d-%H%M%S).tar.gz"
VPS_ROOT=/var/lib/khan-cloud/vps
IMAGE_DIR="$VPS_ROOT/images"
BASE_IMAGE="$IMAGE_DIR/ubuntu-24.04-base.qcow2"
IMAGE_URL="https://cloud-images.ubuntu.com/releases/noble/release/ubuntu-24.04-server-cloudimg-amd64.img"
SUM_URL="https://cloud-images.ubuntu.com/releases/noble/release/SHA256SUMS"
NETWORK=kc-vps-net

echo "===== KHAN CLOUD R7425 HYPERVISOR ACTIVATION ====="
echo "===== SAFETY PRECHECK ====="
test -e /dev/kvm || { echo "ERROR: /dev/kvm missing"; exit 1; }
grep -qE '(svm|vmx)' /proc/cpuinfo || { echo "ERROR: CPU virtualization flag missing"; exit 1; }
ip route | grep -q '192.168.250.0/24' && { echo "ERROR: 192.168.250.0/24 already routed; refusing NAT collision."; exit 1; } || true
test -f /var/lib/khan-cloud-agent/credentials.json || { echo "ERROR: existing Khan Cloud credentials missing"; exit 1; }

echo "===== BACKUP ====="
tar -czf "$BACKUP" --ignore-failed-read \
  /opt/khan-cloud/runtime/node-agent \
  /etc/khan-cloud-agent \
  /var/lib/khan-cloud-agent \
  /etc/systemd/system/khan-cloud-agent.service 2>/dev/null || true

echo "===== INSTALL SAFE HYPERVISOR PACKAGES ====="
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y \
  qemu-kvm qemu-utils libvirt-daemon-system libvirt-clients \
  virtinst cloud-image-utils curl ca-certificates

echo "===== LIBVIRT RUNTIME ====="
systemctl enable --now libvirtd.service
systemctl is-active --quiet libvirtd.service
usermod -aG kvm,libvirt khan-cloud-agent

echo "===== KHAN CLOUD VPS STORAGE ====="
install -d -m 0755 -o khan-cloud-agent -g khan-cloud-agent "$VPS_ROOT" "$IMAGE_DIR" "$VPS_ROOT/instances"

echo "===== KHAL CLOUD NAT NETWORK ====="
cat >/tmp/kc-vps-net.xml <<'EOF'
<network>
  <name>kc-vps-net</name>
  <forward mode='nat'/>
  <bridge name='virbr250' stp='on' delay='0'/>
  <ip address='192.168.250.1' netmask='255.255.255.0'>
    <dhcp><range start='192.168.250.10' end='192.168.250.240'/></dhcp>
  </ip>
</network>
EOF
if ! virsh -c qemu:///system net-info "$NETWORK" >/dev/null 2>&1; then
  virsh -c qemu:///system net-define /tmp/kc-vps-net.xml
fi
virsh -c qemu:///system net-autostart "$NETWORK"
virsh -c qemu:///system net-start "$NETWORK" >/dev/null 2>&1 || true
virsh -c qemu:///system net-info "$NETWORK"

echo "===== UBUNTU 24.04 CLOUD IMAGE ====="
if [[ ! -s "$BASE_IMAGE" ]]; then
  curl -fL "$IMAGE_URL" -o "$BASE_IMAGE.tmp"
  curl -fL "$SUM_URL" -o /tmp/kc-SHA256SUMS
  expected="$(awk '$2=="*ubuntu-24.04-server-cloudimg-amd64.img" || $2=="ubuntu-24.04-server-cloudimg-amd64.img"{print $1;exit}' /tmp/kc-SHA256SUMS)"
  test -n "$expected" || { echo "ERROR: image checksum not found"; rm -f "$BASE_IMAGE.tmp"; exit 1; }
  actual="$(sha256sum "$BASE_IMAGE.tmp" | awk '{print $1}')"
  [[ "$expected" == "$actual" ]] || { echo "ERROR: Ubuntu image checksum mismatch"; rm -f "$BASE_IMAGE.tmp"; exit 1; }
  mv "$BASE_IMAGE.tmp" "$BASE_IMAGE"
fi
chmod 0644 "$BASE_IMAGE"
qemu-img info "$BASE_IMAGE" | head -20

echo "===== DEPLOY FIXED KHAN CLOUD AGENT ====="
systemctl stop khan-cloud-agent.service || true
cp -a "$AGENT_PAYLOAD/khan_agent/." /opt/khan-cloud/runtime/node-agent/khan_agent/
cp -a "$AGENT_PAYLOAD/requirements.txt" /opt/khan-cloud/runtime/node-agent/requirements.txt
/opt/khan-cloud/runtime/node-agent/.venv/bin/pip install -q -r /opt/khan-cloud/runtime/node-agent/requirements.txt
install -m 0644 "$HERE/khan-cloud-agent.service" /etc/systemd/system/khan-cloud-agent.service

python3 - <<'PY'
from pathlib import Path
import yaml
p=Path("/etc/khan-cloud-agent/config.yaml")
raw=yaml.safe_load(p.read_text()) or {}
raw.setdefault("agent",{})["heartbeat_interval_seconds"]=10
v=raw.setdefault("virtualization",{})
v["execution_enabled"]=True
v["network_name"]="kc-vps-net"
v["storage_root"]="/var/lib/khan-cloud/vps"
v["base_image_path"]="/var/lib/khan-cloud/vps/images/ubuntu-24.04-base.qcow2"
p.write_text(yaml.safe_dump(raw,sort_keys=False))
PY
chown root:khan-cloud-agent /etc/khan-cloud-agent/config.yaml
chmod 0640 /etc/khan-cloud-agent/config.yaml

systemctl daemon-reload
systemctl enable --now khan-cloud-agent.service

echo "===== CONTINUOUS HEARTBEAT STABILITY ====="
sleep 32
systemctl is-active --quiet khan-cloud-agent.service
restarts="$(systemctl show khan-cloud-agent.service -p NRestarts --value)"
echo "NRestarts=$restarts"
[[ "$restarts" -le 1 ]] || { journalctl -u khan-cloud-agent -n 80 --no-pager; echo "ERROR: agent restart instability"; exit 1; }

echo "===== VIRTUALIZATION VERIFY ====="
runuser -u khan-cloud-agent -- virsh -c qemu:///system list --all
runuser -u khan-cloud-agent -- test -r "$BASE_IMAGE"
systemctl is-active libvirtd.service
systemctl is-active khan-cloud-agent.service

echo
echo "SUCCESS: R7425 HYPERVISOR ACTIVATED"
echo "Network: kc-vps-net / 192.168.250.0/24 NAT"
echo "Storage: $VPS_ROOT"
echo "Base image: $BASE_IMAGE"
echo "Backup: $BACKUP"
