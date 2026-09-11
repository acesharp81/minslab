#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Run with sudo: sudo scripts/backfill_quick_vod.sh ..." >&2
  exit 1
fi
if [[ $# -lt 3 ]]; then
  echo "Usage: $0 BROADCAST_ID PLAYLIST_URL PLAYLIST_START_AT [--dry-run]" >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
IMAGE="${POC07_IMAGE:-poc07-national-assembly-api:local}"
RUNTIME_DIR="$(mktemp -d /tmp/poc07-qvod-backfill.XXXXXX)"
trap 'rm -rf -- "${RUNTIME_DIR}"' EXIT
umask 077

ENV_FILE="${RUNTIME_DIR}/backfill.env"
awk -F= '
  $1 == "DATABASE_URL" || $1 == "RAW_DATA_DIR" || $1 == "PROCESSED_DATA_DIR" ||
  $1 == "MISTRAL_API_KEY" || $1 == "MISTRAL_BASE_URL" ||
  $1 == "MISTRAL_MONTHLY_CREDIT_USD" ||
  $1 == "MISTRAL_INPUT_USD_PER_MILLION" ||
  $1 == "MISTRAL_OUTPUT_USD_PER_MILLION" ||
  $1 == "EXECUTIVE_TRANSCRIPTION_MODEL" ||
  $1 == "EXECUTIVE_TRANSCRIPTION_USD_PER_MINUTE" { print }
' "${PROJECT_DIR}/.env" > "${ENV_FILE}"
chmod 600 "${ENV_FILE}"

BROADCAST_ID="$1"
PLAYLIST_URL="$2"
PLAYLIST_START_AT="$3"
shift 3
docker run --rm --network poc07-national-assembly \
  --env-file "${ENV_FILE}" -v "${PROJECT_DIR}/data:/app/data" \
  "${IMAGE}" python -m app.ingestion.quick_vod_backfill \
  --broadcast-id "${BROADCAST_ID}" --playlist-url "${PLAYLIST_URL}" \
  --playlist-start-at "${PLAYLIST_START_AT}" "$@"
