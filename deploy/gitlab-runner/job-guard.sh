#!/usr/bin/env bash
set -euo pipefail

expected_workflow='acesharp81/minslab/.github/workflows/sync-gitlab-projects.yml@refs/heads/main'
if [[ "${GITHUB_REPOSITORY:-}" != acesharp81/minslab \
   || "${GITHUB_REF:-}" != refs/heads/main \
   || "${GITHUB_WORKFLOW_REF:-}" != "${expected_workflow}" ]]; then
  echo "This runner only accepts the service sync workflow on minslab main." >&2
  exit 1
fi
case "${GITHUB_EVENT_NAME:-}" in
  workflow_dispatch) ;;
  *)
    echo "This runner does not execute pull request or other event jobs." >&2
    exit 1
    ;;
esac
# Reject old automatic/manual runs: their payload has no explicit source approval.
# This hook lives in the read-only image, outside the checkout.
python3 - <<'PYTHON'
import json
import os
import re
import sys

try:
    with open(os.environ["GITHUB_EVENT_PATH"], encoding="utf-8") as event_file:
        inputs = json.load(event_file).get("inputs") or {}
    valid = (
        inputs.get("approved") in (True, "true")
        and inputs.get("project") in ("kjon", "home", "check", "baton", "all")
        and re.fullmatch(r"[0-9a-f]{40}", inputs.get("source_sha", ""))
    )
except (OSError, KeyError, ValueError, TypeError, AttributeError):
    valid = False
if not valid:
    sys.exit("Manual project selection and explicit source SHA approval are required.")
PYTHON
