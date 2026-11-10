#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if docker container inspect poc13-handover >/dev/null 2>&1; then
  echo 'poc13-handover 컨테이너가 이미 있습니다. 해당 컨테이너 상태를 확인하세요.' >&2
  exit 1
fi
env_args=()
if [[ -f .env ]]; then env_args=(--env-file .env); fi
network_args=()
if docker network inspect minslab-ai-budget >/dev/null 2>&1; then network_args=(--network minslab-ai-budget); fi
docker run -d --name poc13-handover --restart unless-stopped \
  --read-only --tmpfs /tmp:size=268435456,mode=1777 \
  --cap-drop ALL --security-opt no-new-privileges \
  --memory 1536m --cpus 2 \
  -p 127.0.0.1:18130:8000 \
  --mount type=volume,source=poc13-handover-data,target=/app/data \
  "${network_args[@]}" "${env_args[@]}" -e HANDOVER_DATA_DIR=/app/data \
  poc13-handover:1.6.7
