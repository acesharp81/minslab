#!/usr/bin/env bash
set -euo pipefail

deploy_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
units=(
  poc08-collector.service poc08-collector.timer
  poc08-retry.service poc08-retry.timer
  poc08-midday.service poc08-midday.timer
  poc08-midday-retry.service poc08-midday-retry.timer
  poc08-report.service poc08-report.timer
)

for unit in "${units[@]}"; do
  install -m 0644 "${deploy_dir}/${unit}" "/etc/systemd/system/${unit}"
done
systemctl daemon-reload
systemctl enable --now \
  poc08-collector.timer poc08-retry.timer \
  poc08-midday.timer poc08-midday-retry.timer poc08-report.timer
systemctl list-timers 'poc08-*' --no-pager
