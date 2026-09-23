#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p .runtime/bin
if command -v node >/dev/null && [[ "$(node -p 'process.versions.node.split(".")[0]')" -ge 24 ]]; then
  cp "$(command -v node)" .runtime/bin/node
else
  sudo -n docker image inspect node:24-bookworm >/dev/null 2>&1 || sudo -n docker pull node:24-bookworm
  container="$(sudo -n docker create node:24-bookworm)"
  trap 'sudo -n docker rm -f "$container" >/dev/null 2>&1 || true' EXIT
  sudo -n docker cp "$container:/usr/local/bin/node" .runtime/bin/node
  sudo -n chown "$(id -u):$(id -g)" .runtime/bin/node
fi
chmod +x .runtime/bin/node
.runtime/bin/node --version
