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
  workflow_dispatch|push) ;;
  *)
    echo "This runner does not execute pull request or other event jobs." >&2
    exit 1
    ;;
esac
# Push jobs require the restored project-only policy; manual jobs still require approval.
# This hook lives in the read-only image, outside the checkout.
python3 - <<'PYTHON'
import json
import os
import re
import sys

try:
    with open(os.environ["GITHUB_EVENT_PATH"], encoding="utf-8") as event_file:
        event = json.load(event_file)
    inputs = event.get("inputs") or {}
    valid = (
        inputs.get("approved") in (True, "true")
        and inputs.get("project") in ("kjon", "home", "check", "baton", "all")
        and re.fullmatch(r"[0-9a-f]{40}", inputs.get("source_sha", ""))
    )
    if os.environ["GITHUB_EVENT_NAME"] == "push":
        after = event.get("after", "")
        valid = (
            os.environ.get("GITHUB_WORKFLOW") == "Sync service projects to GitLab (automatic and manual)"
            and event.get("ref") == "refs/heads/main"
            and not event.get("deleted")
            and re.fullmatch(r"[0-9a-f]{40}", after)
            and after != "0" * 40
            and after == os.environ.get("GITHUB_SHA")
        )
except (OSError, KeyError, ValueError, TypeError, AttributeError):
    valid = False
if not valid:
    sys.exit("A pinned main push from the current sync workflow or an approved manual source is required.")
PYTHON
