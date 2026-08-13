#!/usr/bin/env bash
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "ERROR: run with sudo/root."
  exit 1
fi

SOURCE_DIR="${1:?Usage: apply-runtime-update.sh <agent-source-dir> <config-file>}"
CONFIG_SOURCE="${2:?Usage: apply-runtime-update.sh <agent-source-dir> <config-file>}"

RUNTIME=/opt/khan-cloud/runtime/node-agent
ETC=/etc/khan-cloud-agent
STATE=/var/lib/khan-cloud-agent
SERVICE=khan-cloud-agent.service

BACKUP="/tmp/khan-cloud-agent-update-$(date +%Y%m%d-%H%M%S).tar.gz"

echo "===== PRE-FLIGHT ====="

test -f "$STATE/credentials.json" || {
  echo "ERROR: existing node credentials are missing."
  exit 1
}

test -d "$SOURCE_DIR/khan_agent" || {
  echo "ERROR: invalid agent source directory."
  exit 1
}

test -f "$CONFIG_SOURCE" || {
  echo "ERROR: update configuration is missing."
  exit 1
}

test -x "$RUNTIME/.venv/bin/python" || {
  echo "ERROR: existing agent Python environment is unavailable."
  exit 1
}

echo "===== BACKUP ====="

tar -czf "$BACKUP" \
  "$RUNTIME/khan_agent" \
  "$ETC/config.yaml" \
  "$STATE/credentials.json" \
  /etc/systemd/system/khan-cloud-agent.service \
  2>/dev/null

echo "===== STOP AGENT ====="

systemctl stop "$SERVICE"

echo "===== UPDATE RUNTIME ====="

for component in khan_agent deploy tests; do
  test -d "$SOURCE_DIR/$component" || {
    echo "ERROR: update payload missing required component: $component"
    exit 1
  }
done

rm -rf   "$RUNTIME/khan_agent"   "$RUNTIME/deploy"   "$RUNTIME/tests"

cp -a "$SOURCE_DIR/khan_agent" "$RUNTIME/khan_agent"
cp -a "$SOURCE_DIR/deploy" "$RUNTIME/deploy"
cp -a "$SOURCE_DIR/tests" "$RUNTIME/tests"

chown -R root:root   "$RUNTIME/khan_agent"   "$RUNTIME/deploy"   "$RUNTIME/tests"

chmod -R go-w   "$RUNTIME/khan_agent"   "$RUNTIME/deploy"   "$RUNTIME/tests"

echo "===== UPDATE CONFIG ====="

install -o root -g khan-cloud-agent -m 0640 \
  "$CONFIG_SOURCE" \
  "$ETC/config.yaml"

echo "===== COMPILE ====="

"$RUNTIME/.venv/bin/python" -m compileall -q \
  "$RUNTIME/khan_agent"

echo "===== TESTS ====="

cd "$RUNTIME"
PYTHONPATH=. "$RUNTIME/.venv/bin/python" -m pytest -q

echo "===== START AGENT ====="

systemctl start "$SERVICE"

sleep 3

systemctl is-active --quiet "$SERVICE"

echo "===== HEARTBEAT ====="

cd "$RUNTIME"

runuser -u khan-cloud-agent -- \
  env PYTHONPATH="$RUNTIME" \
  "$RUNTIME/.venv/bin/python" \
  -m khan_agent \
  --config "$ETC/config.yaml" \
  --heartbeat-once

echo
echo "SUCCESS: KHAN CLOUD NODE RUNTIME UPDATED"
echo "Backup: $BACKUP"
