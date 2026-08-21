#!/usr/bin/env bash
set -euo pipefail

VMID="${1:-}"
if [[ ! "$VMID" =~ ^[0-9]+$ ]] || [ "$VMID" -lt 100 ]; then
    echo "Usage: $0 <windows-template-vmid>"
    exit 2
fi

MARKER="khan-gaming-template-v1"
VALIDATOR='C:\ProgramData\KhanCloud\Agent\runtime\deploy\validate-windows-gaming-template.ps1'

echo "============================================================"
echo " KHAN CLOUD — SEAL WINDOWS GAMING TEMPLATE"
echo "============================================================"

command -v qm >/dev/null

CONFIG="$(qm config "$VMID")"
if grep -qE '^template:\s*1\s*$' <<<"$CONFIG"; then
    echo "PASS — VM $VMID is already a template"
    if ! grep -q "$MARKER" <<<"$CONFIG"; then
        echo "FAIL — existing template lacks Khan contract marker"
        exit 1
    fi
    exit 0
fi

STATUS="$(qm status "$VMID" | awk '{print $2}')"
if [ "$STATUS" != "running" ]; then
    echo "Starting validation source VM $VMID"
    qm start "$VMID"
fi

for _ in $(seq 1 60); do
    if qm agent "$VMID" ping >/dev/null 2>&1; then break; fi
    sleep 5
done
qm agent "$VMID" ping >/dev/null

echo "===== GUEST CONTRACT VALIDATION ====="
OUTPUT="$(qm guest exec "$VMID" -- powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$VALIDATOR" -JsonOnly)"
python3 - "$OUTPUT" <<'PY2'
import json,sys
outer=json.loads(sys.argv[1])
if int(outer.get('exitcode', 1)) != 0:
    raise SystemExit('FAIL — Windows template validator returned failure')
raw=outer.get('out-data','').strip()
data=json.loads(raw)
print('CONTRACT:', data.get('contract_version'))
print('VALID:', data.get('valid'))
print('FAILED:', data.get('failed_checks'))
if data.get('contract_version') != 'kg006-v1' or data.get('valid') is not True:
    raise SystemExit('FAIL — invalid Khan Windows template contract')
PY2

qm shutdown "$VMID" --timeout 120 || qm stop "$VMID"
for _ in $(seq 1 30); do
    [ "$(qm status "$VMID" | awk '{print $2}')" = "stopped" ] && break
    sleep 2
done

DESCRIPTION="Khan Cloud Windows Gaming Golden Template\nContract: kg006-v1\nMarker: $MARKER"
qm set "$VMID" --description "$DESCRIPTION" --tags "$MARKER" --agent enabled=1
qm template "$VMID"

FINAL="$(qm config "$VMID")"
grep -qE '^template:\s*1\s*$' <<<"$FINAL"
grep -q "$MARKER" <<<"$FINAL"
grep -qE '^agent:\s*enabled=1' <<<"$FINAL"

echo "PASS — VM $VMID sealed as Khan Cloud gaming template"
