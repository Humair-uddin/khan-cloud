#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "============================================================"
echo " KHAN CLOUD - FULL TEST SUITE"
echo "============================================================"

echo
echo "===== BACKEND ====="
cd "$ROOT/backend"
"$ROOT/backend/.venv/bin/python" -m pytest -q

echo
echo "===== NODE AGENT ====="
cd "$ROOT/node-agent"
"$ROOT/node-agent/.venv/bin/python" -m pytest -q

echo
echo "===== INSTALLER ENGINE ====="
cd "$ROOT/installer-engine"
"$ROOT/backend/.venv/bin/python" -m pytest -q

echo
echo "============================================================"
echo " ALL KHAN CLOUD TEST SUITES PASSED"
echo "============================================================"
