#!/usr/bin/env bash
set -euo pipefail
if [[ ${EUID} -ne 0 ]]; then
  echo "Run with sudo: sudo scripts/install_runtime_check.sh" >&2
  exit 1
fi
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
# Verify before installation; this does not restart any production container.
python3 "${SCRIPT_DIR}/check_runtime.py" --scope all --repair-restart-policy
install -m 0644 "${PROJECT_DIR}/deploy/systemd/poc07-runtime-check.service" /etc/systemd/system/poc07-runtime-check.service
install -m 0644 "${PROJECT_DIR}/deploy/systemd/poc07-runtime-check.timer" /etc/systemd/system/poc07-runtime-check.timer
systemctl daemon-reload
systemctl enable --now poc07-runtime-check.timer
systemctl start poc07-runtime-check.service
