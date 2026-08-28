#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Run with sudo: sudo scripts/deploy_secure_workers.sh [all|summary|meeting|official|executive]" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ROOT_DIR="$(cd "${PROJECT_DIR}/../.." && pwd)"
ROOT_ENV="${ROOT_DIR}/.env"
PROJECT_ENV="${PROJECT_DIR}/.env"
IMAGE="${POC07_IMAGE:-poc07-national-assembly-api:local}"
NETWORK="poc07-national-assembly"
TARGET="${1:-all}"

for required in "${ROOT_ENV}" "${PROJECT_ENV}"; do
  if [[ ! -f "${required}" ]]; then
    echo "Required environment file is missing: ${required}" >&2
    exit 1
  fi
done

umask 077
RUNTIME_DIR="$(mktemp -d /tmp/poc07-worker-env.XXXXXX)"
trap 'rm -rf -- "${RUNTIME_DIR}"' EXIT

make_env_file() {
  local output="$1"
  local allowlist="$2"
  awk -F= -v allowlist="${allowlist}" '
    BEGIN {
      count = split(allowlist, keys, ",")
      for (i = 1; i <= count; i++) allowed[keys[i]] = i
    }
    /^[[:space:]]*#/ || !index($0, "=") { next }
    $1 in allowed {
      value = substr($0, index($0, "=") + 1)
      if (value != "" || !($1 in selected)) selected[$1] = $0
    }
    END {
      for (i = 1; i <= count; i++) {
        key = keys[i]
        if (key in selected) print selected[key]
      }
    }
  ' "${ROOT_ENV}" "${PROJECT_ENV}" > "${output}"
  chmod 600 "${output}"
}

deploy_worker() {
  local short_name="$1"
  local module="$2"
  local interval="$3"
  local allowlist="$4"
  local with_data_volume="$5"
  local name="poc07-national-assembly-${short_name}-worker"
  local env_file="${RUNTIME_DIR}/${short_name}.env"
  local rollback="${name}-secret-scope-rollback-$(date -u +%Y%m%d%H%M%S)"

  make_env_file "${env_file}" "${allowlist}"
  if ! /usr/bin/grep -Eq '^DATABASE_URL=.+$' "${env_file}"; then
    echo "${short_name}: DATABASE_URL is not configured" >&2
    exit 1
  fi
  if ! /usr/bin/grep -Eq '^MISTRAL_API_KEY=.+$' "${env_file}"; then
    echo "${short_name}: MISTRAL_API_KEY is not configured" >&2
    exit 1
  fi

  if docker container inspect "${name}" >/dev/null 2>&1; then
    docker stop "${name}" >/dev/null
    docker rename "${name}" "${rollback}"
  else
    rollback=""
  fi

  local args=(
    docker run -d
    --name "${name}"
    --restart unless-stopped
    --network "${NETWORK}"
    --env-file "${env_file}"
    -w /app
    -u appuser
  )
  if [[ "${with_data_volume}" == "yes" ]]; then
    args+=( -v "${PROJECT_DIR}/data:/app/data" )
  fi
  args+=( "${IMAGE}" python -m "${module}" --interval "${interval}" )

  if ! "${args[@]}" >/dev/null; then
    docker rm -f "${name}" >/dev/null 2>&1 || true
    if [[ -n "${rollback}" ]]; then
      docker rename "${rollback}" "${name}"
      docker start "${name}" >/dev/null
    fi
    echo "${short_name}: deployment failed; previous container restored" >&2
    exit 1
  fi
  echo "${short_name}: deployed with allowlisted environment"
}

COMMON_MISTRAL="DATABASE_URL,AI_ENRICHMENT_ENABLED,LLM_PROVIDER,LLM_MODEL,MISTRAL_API_KEY,MISTRAL_BASE_URL,MISTRAL_MONTHLY_TOKEN_LIMIT,MISTRAL_MONTHLY_CREDIT_USD,MISTRAL_INPUT_USD_PER_MILLION,MISTRAL_OUTPUT_USD_PER_MILLION"
EXECUTIVE_AUDIO="${COMMON_MISTRAL},RAW_DATA_DIR,EXECUTIVE_TRANSCRIPTION_MODEL,EXECUTIVE_AUDIO_CHUNK_SECONDS,EXECUTIVE_TRANSCRIPTION_USD_PER_MINUTE"

case "${TARGET}" in
  all)
    deploy_worker "summary" "app.ingestion.summary_worker" "2" "${COMMON_MISTRAL},GEMINI_API_KEY,OPENROUTER_API_KEY,OPENROUTER_BASE_URL,OPENROUTER_DAILY_LIMIT" "no"
    deploy_worker "meeting-brief" "app.ingestion.meeting_brief_worker" "60" "${COMMON_MISTRAL}" "no"
    deploy_worker "official-minutes" "app.ingestion.official_minutes_worker" "3600" "${COMMON_MISTRAL},NATIONAL_ASSEMBLY_API_KEY,RAW_DATA_DIR" "yes"
    deploy_worker "executive-caption" "app.ingestion.executive_caption_worker" "5" "${EXECUTIVE_AUDIO}" "yes"
    ;;
  summary)
    deploy_worker "summary" "app.ingestion.summary_worker" "2" "${COMMON_MISTRAL},GEMINI_API_KEY,OPENROUTER_API_KEY,OPENROUTER_BASE_URL,OPENROUTER_DAILY_LIMIT" "no"
    ;;
  meeting)
    deploy_worker "meeting-brief" "app.ingestion.meeting_brief_worker" "60" "${COMMON_MISTRAL}" "no"
    ;;
  official)
    deploy_worker "official-minutes" "app.ingestion.official_minutes_worker" "3600" "${COMMON_MISTRAL},NATIONAL_ASSEMBLY_API_KEY,RAW_DATA_DIR" "yes"
    ;;
  executive)
    deploy_worker "executive-caption" "app.ingestion.executive_caption_worker" "5" "${EXECUTIVE_AUDIO}" "yes"
    ;;
  *)
    echo "Unknown target: ${TARGET}" >&2
    exit 2
    ;;
esac
