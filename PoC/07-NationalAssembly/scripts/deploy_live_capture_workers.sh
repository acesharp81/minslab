#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Run with sudo: sudo scripts/deploy_live_capture_workers.sh" >&2
  exit 1
fi

if [[ $# -gt 1 || ( $# -eq 1 && $1 != "--monitor-only" ) ]]; then
  echo "Usage: $0 [--monitor-only]" >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
PROJECT_ENV="${PROJECT_DIR}/.env"
IMAGE="${POC07_IMAGE:-poc07-national-assembly-api:local}"
NETWORK="poc07-national-assembly"
RUNTIME_DIR="$(mktemp -d /tmp/poc07-live-capture.XXXXXX)"
trap 'rm -rf -- "${RUNTIME_DIR}"' EXIT
umask 077

ENV_FILE="${RUNTIME_DIR}/capture.env"
awk -F= '
  $1 == "DATABASE_URL" || $1 == "RAW_DATA_DIR" || $1 == "PROCESSED_DATA_DIR" ||
  $1 == "MISTRAL_API_KEY" || $1 == "MISTRAL_BASE_URL" ||
  $1 == "MISTRAL_MONTHLY_CREDIT_USD" ||
  $1 == "EXECUTIVE_TRANSCRIPTION_MODEL" ||
  $1 == "EXECUTIVE_AUDIO_CHUNK_SECONDS" ||
  $1 == "EXECUTIVE_TRANSCRIPTION_USD_PER_MINUTE" { print }
' "${PROJECT_ENV}" > "${ENV_FILE}"
chmod 600 "${ENV_FILE}"

deploy() {
  local name="$1"
  shift
  local rollback="${name}-rollback-$(date -u +%Y%m%d%H%M%S)"
  if docker container inspect "${name}" >/dev/null 2>&1; then
    docker stop "${name}" >/dev/null
    docker rename "${name}" "${rollback}"
  else
    rollback=""
  fi
  if ! docker run -d --name "${name}" --restart unless-stopped \
      --network "${NETWORK}" --env-file "${ENV_FILE}" \
      -v "${PROJECT_DIR}/data:/app/data" -w /app -u appuser \
      "${IMAGE}" "$@" >/dev/null; then
    docker rm -f "${name}" >/dev/null 2>&1 || true
    if [[ -n "${rollback}" ]]; then docker rename "${rollback}" "${name}"; docker start "${name}" >/dev/null; fi
    exit 1
  fi
  sleep 2
  if ! docker ps --format '{{.Names}}' | grep -Fxq "${name}"; then
    docker logs --tail 30 "${name}" >&2 || true
    docker rm -f "${name}" >/dev/null 2>&1 || true
    if [[ -n "${rollback}" ]]; then docker rename "${rollback}" "${name}"; docker start "${name}" >/dev/null; fi
    exit 1
  fi
  if [[ -n "${rollback}" ]]; then docker rm "${rollback}" >/dev/null; fi
  echo "${name}: deployed"
}

deploy poc07-national-assembly-live-monitor \
  python -m app.ingestion.live_monitor --interval 30
if [[ ${1:-} == "--monitor-only" ]]; then
  exit 0
fi
deploy poc07-national-assembly-caption-worker \
  python -m app.ingestion.caption_worker --workers 4
deploy poc07-national-assembly-executive-caption-worker \
  python -m app.ingestion.executive_caption_worker --interval 5
