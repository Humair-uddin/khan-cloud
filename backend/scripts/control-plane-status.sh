#!/usr/bin/env bash
set -euo pipefail

echo "===== SERVICE ====="
systemctl --no-pager --full status khan-cloud-control-plane.service || true

echo
echo "===== PORT 8000 ====="
ss -lntp | grep ':8000' || true

echo
echo "===== HEALTH ====="
curl -fsS http://127.0.0.1:8000/health
echo

echo
echo "===== READINESS ====="
curl -fsS http://127.0.0.1:8000/ready
echo

echo
echo "===== VERSION ====="
curl -fsS http://127.0.0.1:8000/version
echo

echo
echo "===== UI ====="
curl -fsSI http://127.0.0.1:8000/ui/ | head -1
