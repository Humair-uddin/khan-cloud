#!/usr/bin/env bash
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "ERROR: Khan Cloud bootstrap must run with sudo/root."
  exit 1
fi

STATE_DIR=/var/lib/khan-cloud-bootstrap
CHECKPOINTS="$STATE_DIR/bootstrap.checkpoints"
WORK=/var/lib/khan-cloud-bootstrap/work
SELF="${BASH_SOURCE[0]}"

mkdir -p "$STATE_DIR" "$WORK"
chmod 0700 "$STATE_DIR" "$WORK"
touch "$CHECKPOINTS"
chmod 0600 "$CHECKPOINTS"

stage_done() { grep -Fxq "$1" "$CHECKPOINTS"; }
mark_done() { stage_done "$1" || printf '%s\n' "$1" >> "$CHECKPOINTS"; }

safe_apt_install() {
  local package="$1"
  if ! command -v apt-get >/dev/null 2>&1; then
    echo "ERROR: unsupported bootstrap platform; apt-get is required for safe remediation."
    exit 1
  fi
  if ! stage_done apt_updated; then
    DEBIAN_FRONTEND=noninteractive apt-get update
    mark_done apt_updated
  fi
  DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "$package"
}

echo "===== KHAN CLOUD UNIVERSAL NODE BOOTSTRAP ====="

if ! stage_done platform_checked; then
  if [[ ! -r /etc/os-release ]]; then
    echo "ERROR: unable to detect operating system."
    exit 1
  fi
  . /etc/os-release
  case "${ID:-}" in
    ubuntu|debian) ;;
    *) echo "ERROR: unsupported OS for v1 bootstrap: ${ID:-unknown}"; exit 1 ;;
  esac
  case "$(uname -m)" in
    x86_64|amd64) ;;
    *) echo "ERROR: unsupported architecture for v1 bootstrap: $(uname -m)"; exit 1 ;;
  esac
  mark_done platform_checked
fi

if ! stage_done safe_prerequisites; then
  if ! command -v python3 >/dev/null 2>&1; then
    safe_apt_install python3
  fi
  probe="$(mktemp -d /tmp/khan-cloud-bootstrap-venv.XXXXXX)"
  if ! python3 -m venv "$probe/venv" >/dev/null 2>&1; then
    rm -rf "$probe"
    safe_apt_install python3-venv
  else
    rm -rf "$probe"
  fi
  if ! test -r /etc/ssl/certs/ca-certificates.crt; then
    safe_apt_install ca-certificates
  fi
  mark_done safe_prerequisites
fi

if ! stage_done payload_extracted; then
  rm -rf "$WORK/payload"
  mkdir -p "$WORK/payload"
  payload_line="$(awk '/^__KC_PAYLOAD_BELOW__$/ {print NR + 1; exit}' "$SELF")"
  if [[ -z "$payload_line" ]]; then
    echo "ERROR: embedded payload marker not found."
    exit 1
  fi
  tail -n +"$payload_line" "$SELF" \
    | base64 --decode \
    | tar -xzf - -C "$WORK/payload"
  mark_done payload_extracted
fi

if ! stage_done installer_completed; then
  "$WORK/payload/install.sh"
  mark_done installer_completed
fi

mark_done completed
echo
echo "SUCCESS: KHAN CLOUD UNIVERSAL NODE BOOTSTRAP COMPLETE"
exit 0

__KC_PAYLOAD_BELOW__
