#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
exec .venv/bin/python -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port "${HANDOVER_PORT:-18130}" --workers 1 --proxy-headers
