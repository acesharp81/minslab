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
  push|workflow_dispatch) ;;
  *)
    echo "This runner does not execute pull request or other event jobs." >&2
    exit 1
    ;;
esac
