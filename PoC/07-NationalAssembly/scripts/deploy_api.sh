#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Run with sudo: sudo scripts/deploy_api.sh" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
PROJECT_ENV="${PROJECT_DIR}/.env"
IMAGE="${POC07_IMAGE:-poc07-national-assembly-api:local}"
NAME="poc07-national-assembly-api"
NETWORK="poc07-national-assembly"
ROLLBACK="${NAME}-rollback-$(date -u +%Y%m%d%H%M%S)"

for required in "${PROJECT_ENV}"; do
  if [[ ! -f "${required}" ]]; then
    echo "Required environment file is missing: ${required}" >&2
    exit 1
  fi
done

umask 077
RUNTIME_DIR="$(mktemp -d /tmp/poc07-api-env.XXXXXX)"
trap 'rm -rf -- "${RUNTIME_DIR}"' EXIT
ENV_FILE="${RUNTIME_DIR}/api.env"
ALLOWLIST="DATABASE_URL,NATIONAL_ASSEMBLY_ENV,NATIONAL_ASSEMBLY_LOG_LEVEL,NATIONAL_ASSEMBLY_TIMEZONE,RAW_DATA_DIR,PROCESSED_DATA_DIR,AI_ENRICHMENT_ENABLED,LLM_PROVIDER,LLM_MODEL,OPENROUTER_DAILY_LIMIT,OPENROUTER_GATEWAY_STATUS_URL,MISTRAL_MONTHLY_CREDIT_USD,MISTRAL_INPUT_USD_PER_MILLION,MISTRAL_OUTPUT_USD_PER_MILLION,WATCH_ALERTS_ENABLED,WATCH_TEST_BROADCASTS_ENABLED,WATCH_DIGEST_ENABLED,WATCH_KAKAO_ENABLED,WATCH_LLM_ENABLED,WATCH_LLM_PROVIDER,WATCH_LLM_MODEL,WATCH_KAKAO_REDIRECT_URI,WATCH_PUBLIC_BASE_URL,WATCH_KAKAO_REST_API_KEY,WATCH_KAKAO_CLIENT_SECRET,WATCH_KAKAO_TOKEN_ENCRYPTION_KEY,WATCH_ADMIN_TOKEN,WATCH_SESSION_COOKIE_NAME,WATCH_SESSION_COOKIE_PATH,TOPIC_REPORTS_ENABLED,TOPIC_REPORT_MODEL,TOPIC_REPORT_DAILY_LIMIT,TOPIC_REPORT_USER_DAILY_LIMIT,TOPIC_REPORT_MAX_PERIOD_DAYS"

awk -F= -v allowlist="${ALLOWLIST}" '
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
' "${PROJECT_ENV}" > "${ENV_FILE}"
chmod 600 "${ENV_FILE}"

if ! /usr/bin/grep -Eq '^DATABASE_URL=.+$' "${ENV_FILE}"; then
  echo "DATABASE_URL is not configured" >&2
  exit 1
fi

if docker container inspect "${NAME}" >/dev/null 2>&1; then
  docker stop "${NAME}" >/dev/null
  docker rename "${NAME}" "${ROLLBACK}"
else
  ROLLBACK=""
fi

if ! docker run -d \
  --name "${NAME}" \
  --restart unless-stopped \
  --network "${NETWORK}" \
  --env-file "${ENV_FILE}" \
  -p 127.0.0.1:18070:8070 \
  -v "${PROJECT_DIR}/data:/app/data" \
  -v "${PROJECT_DIR}/web:/app/web:ro" \
  "${IMAGE}" >/dev/null; then
  docker rm -f "${NAME}" >/dev/null 2>&1 || true
  if [[ -n "${ROLLBACK}" ]]; then
    docker rename "${ROLLBACK}" "${NAME}"
    docker start "${NAME}" >/dev/null
  fi
  echo "API deployment failed; previous container restored" >&2
  exit 1
fi

for _ in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:18070/api/health >/dev/null 2>&1; then
    if [[ -n "${ROLLBACK}" ]]; then
      docker rm "${ROLLBACK}" >/dev/null
    fi
    echo "api: deployed with allowlisted environment"
    exit 0
  fi
  sleep 1
done

docker logs --tail 30 "${NAME}" >&2 || true
docker rm -f "${NAME}" >/dev/null 2>&1 || true
if [[ -n "${ROLLBACK}" ]]; then
  docker rename "${ROLLBACK}" "${NAME}"
  docker start "${NAME}" >/dev/null
fi
echo "API health check failed; previous container restored" >&2
exit 1
