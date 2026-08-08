#!/usr/bin/env bash
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "ERROR: run this installer with sudo."
  exit 1
fi

SOURCE_DIR="${1:?Usage: install-runtime.sh <agent-source-dir> <config-file>}"
CONFIG_SOURCE="${2:?Usage: install-runtime.sh <agent-source-dir> <config-file>}"

RUNTIME=/opt/khan-cloud/runtime/node-agent
ETC=/etc/khan-cloud-agent
STATE=/var/lib/khan-cloud-agent
BOOTSTRAP_STATE=/var/lib/khan-cloud-bootstrap
CHECKPOINTS="$BOOTSTRAP_STATE/install-runtime.checkpoints"
SERVICE=/etc/systemd/system/khan-cloud-agent.service
BACKUP="/tmp/khan-cloud-agent-runtime-backup-$(date +%Y%m%d-%H%M%S).tar.gz"

mkdir -p "$BOOTSTRAP_STATE"
touch "$CHECKPOINTS"
chmod 0700 "$BOOTSTRAP_STATE"
chmod 0600 "$CHECKPOINTS"

stage_done() { grep -Fxq "$1" "$CHECKPOINTS"; }
mark_done() { stage_done "$1" || printf '%s\n' "$1" >> "$CHECKPOINTS"; }

safe_apt_install() {
  local package="$1"
  if ! command -v apt-get >/dev/null 2>&1; then
    echo "ERROR: safe automatic prerequisite remediation supports apt-based systems only."
    return 1
  fi
  if ! stage_done apt_updated; then
    DEBIAN_FRONTEND=noninteractive apt-get update
    mark_done apt_updated
  fi
  DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "$package"
}

ensure_python_venv() {
  if ! command -v python3 >/dev/null 2>&1; then
    safe_apt_install python3
  fi

  local probe
  probe="$(mktemp -d /tmp/khan-cloud-venv-probe.XXXXXX)"
  if ! python3 -m venv "$probe/venv" >/dev/null 2>&1; then
    rm -rf "$probe"
    safe_apt_install python3-venv
    probe="$(mktemp -d /tmp/khan-cloud-venv-probe.XXXXXX)"
    python3 -m venv "$probe/venv"
  fi
  rm -rf "$probe"
}

if [[ ! -d "$SOURCE_DIR/khan_agent" ]]; then
  echo "ERROR: invalid agent source directory: $SOURCE_DIR"
  exit 1
fi
if [[ ! -f "$CONFIG_SOURCE" ]]; then
  echo "ERROR: node configuration is missing: $CONFIG_SOURCE"
  exit 1
fi

echo "===== SAFE PREREQUISITES ====="
if ! stage_done safe_prerequisites; then
  ensure_python_venv
  if ! test -r /etc/ssl/certs/ca-certificates.crt; then
    safe_apt_install ca-certificates
  fi
  mark_done safe_prerequisites
fi

echo "===== BACKUP EXISTING AGENT STATE ====="
if ! stage_done backup_created; then
  tar -czf "$BACKUP" \
    --ignore-failed-read \
    /opt/khan-cloud/runtime/node-agent \
    /etc/khan-cloud-agent \
    /var/lib/khan-cloud-agent \
    /etc/systemd/system/khan-cloud-agent.service \
    2>/dev/null || true
  mark_done backup_created
fi

echo "===== SERVICE ACCOUNT ====="
if ! stage_done service_account; then
  if ! getent group khan-cloud-agent >/dev/null; then
    groupadd --system khan-cloud-agent
  fi
  if ! id khan-cloud-agent >/dev/null 2>&1; then
    useradd \
      --system \
      --gid khan-cloud-agent \
      --home-dir "$STATE" \
      --shell /usr/sbin/nologin \
      khan-cloud-agent
  fi
  mark_done service_account
fi

echo "===== INSTALL RUNTIME ====="
if ! stage_done runtime_copied; then
  rm -rf "$RUNTIME"
  mkdir -p "$RUNTIME" "$ETC/plugins" "$STATE"
  cp -a "$SOURCE_DIR/." "$RUNTIME/"
  rm -rf "$RUNTIME/.venv" "$RUNTIME/.pytest_cache"
  find "$RUNTIME" -type d -name __pycache__ -prune -exec rm -rf {} + || true
  chown -R root:root "$RUNTIME"
  chmod -R go-w "$RUNTIME"
  mark_done runtime_copied
fi

echo "===== PYTHON ENVIRONMENT ====="
if ! stage_done python_environment; then
  rm -rf "$RUNTIME/.venv"
  python3 -m venv "$RUNTIME/.venv"
  "$RUNTIME/.venv/bin/pip" install --disable-pip-version-check -q --upgrade pip
  "$RUNTIME/.venv/bin/pip" install --disable-pip-version-check -q -r "$RUNTIME/requirements.txt"
  mark_done python_environment
fi

echo "===== CONFIGURATION ====="
if ! stage_done configuration; then
  install -o root -g khan-cloud-agent -m 0640 "$CONFIG_SOURCE" "$ETC/config.yaml"
  chown -R root:khan-cloud-agent "$ETC"
  chmod 0750 "$ETC" "$ETC/plugins"
  chown -R khan-cloud-agent:khan-cloud-agent "$STATE"
  chmod 0700 "$STATE"
  mark_done configuration
fi

echo "===== INSTALL SYSTEMD UNIT ====="
if ! stage_done systemd_unit; then
  install -o root -g root -m 0644 \
    "$RUNTIME/systemd/khan-cloud-agent.service" \
    "$SERVICE"
  systemctl daemon-reload
  systemd-analyze verify "$SERVICE"
  mark_done systemd_unit
fi

echo "===== AGENT TESTS ====="
if ! stage_done agent_tests; then
  cd "$RUNTIME"
  PYTHONPATH=. "$RUNTIME/.venv/bin/python" -m pytest -q
  mark_done agent_tests
fi

echo "===== ENROLL NODE ====="
if [[ -s "$STATE/credentials.json" ]]; then
  echo "Existing credentials detected; enrollment checkpoint recovered."
  mark_done enrolled
elif ! stage_done enrolled; then
  runuser -u khan-cloud-agent -- \
    "$RUNTIME/.venv/bin/python" -m khan_agent \
    --config "$ETC/config.yaml" \
    --enroll
  if [[ ! -s "$STATE/credentials.json" ]]; then
    echo "ERROR: enrollment did not create credentials."
    exit 1
  fi
  mark_done enrolled
fi

echo "===== REMOVE ONE-TIME ENROLLMENT CODE ====="
if ! stage_done enrollment_code_scrubbed; then
  "$RUNTIME/.venv/bin/python" - "$ETC/config.yaml" <<'PY'
import sys
from pathlib import Path
import yaml
path = Path(sys.argv[1])
raw = yaml.safe_load(path.read_text()) or {}
raw.setdefault("security", {})["deployment_enrollment_code"] = ""
path.write_text(yaml.safe_dump(raw, sort_keys=False))
PY
  chown root:khan-cloud-agent "$ETC/config.yaml"
  chmod 0640 "$ETC/config.yaml"
  mark_done enrollment_code_scrubbed
fi

echo "===== ENABLE PERSISTENT AGENT ====="
if ! stage_done service_enabled; then
  systemctl enable --now khan-cloud-agent.service
  mark_done service_enabled
else
  systemctl start khan-cloud-agent.service
fi

echo "===== HEARTBEAT VERIFICATION ====="
runuser -u khan-cloud-agent -- \
  "$RUNTIME/.venv/bin/python" -m khan_agent \
  --config "$ETC/config.yaml" \
  --heartbeat-once
mark_done heartbeat_verified

echo "===== SERVICE STATE ====="
systemctl is-enabled khan-cloud-agent.service
systemctl is-active khan-cloud-agent.service

echo "===== SAFE CREDENTIAL SUMMARY ====="
"$RUNTIME/.venv/bin/python" - <<'PY'
import json
from pathlib import Path
data = json.loads(Path("/var/lib/khan-cloud-agent/credentials.json").read_text())
print("node_id:", data.get("node_id"))
print("node_secret: [HIDDEN]")
PY

mark_done completed
echo
echo "SUCCESS: KHAN CLOUD NODE AGENT INSTALLED / RESUMED"
echo "Checkpoint file: $CHECKPOINTS"
