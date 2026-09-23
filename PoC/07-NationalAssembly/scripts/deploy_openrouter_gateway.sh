#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Run with sudo: sudo scripts/deploy_openrouter_gateway.sh" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
PROJECT_ENV="${PROJECT_DIR}/.env"
IMAGE="${POC07_IMAGE:-poc07-national-assembly-api:local}"
NAME="poc07-openrouter-gateway"
NETWORK="poc07-national-assembly"
ROLLBACK="${NAME}-rollback-$(date -u +%Y%m%d%H%M%S)"
ENV_FILE="$(mktemp /tmp/poc07-openrouter-gateway.XXXXXX)"
trap 'rm -f -- "${ENV_FILE}"' EXIT
umask 077

awk -F= '$1 == "OPENROUTER_API_KEY" { print; found=1 } END { if (!found) exit 1 }' \
  "${PROJECT_ENV}" > "${ENV_FILE}"
awk -F= '$1 == "OPENROUTER_METER_TOKEN" { print }' "${PROJECT_ENV}" >> "${ENV_FILE}"
{
  echo 'OPENROUTER_GATEWAY_DB=/app/data/openrouter_gateway.sqlite3'
  echo 'OPENROUTER_OFFICIAL_DAILY_LIMIT=1000'
  echo 'OPENROUTER_OPERATIONAL_DAILY_LIMIT=950'
  echo 'OPENROUTER_RPM_LIMIT=18'
  echo 'OPENROUTER_MAX_INFLIGHT=4'
  echo 'OPENROUTER_FREE_MODELS=nvidia/nemotron-3-super-120b-a12b:free,liquid/lfm-2.5-2.6b:free,dots-studio/dots-3-note-preview:free'
} >> "${ENV_FILE}"
chmod 600 "${ENV_FILE}"

if docker container inspect "${NAME}" >/dev/null 2>&1; then
  docker stop "${NAME}" >/dev/null
  docker rename "${NAME}" "${ROLLBACK}"
else
  ROLLBACK=""
fi

if ! docker run -d --name "${NAME}" --restart unless-stopped \
  --network "${NETWORK}" --env-file "${ENV_FILE}" \
  -p 127.0.0.1:18071:8071 -v "${PROJECT_DIR}/data:/app/data" \
  "${IMAGE}" uvicorn app.openrouter_gateway:app --app-dir /app/backend \
  --host 0.0.0.0 --port 8071 >/dev/null; then
  docker rm -f "${NAME}" >/dev/null 2>&1 || true
  if [[ -n "${ROLLBACK}" ]]; then docker rename "${ROLLBACK}" "${NAME}"; docker start "${NAME}" >/dev/null; fi
  exit 1
fi

for _ in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:18071/health >/dev/null 2>&1; then
    if [[ -n "${ROLLBACK}" ]]; then docker rm "${ROLLBACK}" >/dev/null; fi
    echo "openrouter-gateway: deployed"
    exit 0
  fi
  sleep 1
done

docker logs --tail 30 "${NAME}" >&2 || true
docker rm -f "${NAME}" >/dev/null 2>&1 || true
if [[ -n "${ROLLBACK}" ]]; then docker rename "${ROLLBACK}" "${NAME}"; docker start "${NAME}" >/dev/null; fi
exit 1
