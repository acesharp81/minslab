#!/usr/bin/env bash
set -euo pipefail

case "${1:-run}" in
  register)
    : "${RUNNER_URL:?RUNNER_URL is required}"
    : "${RUNNER_NAME:?RUNNER_NAME is required}"
    runner_directory=/home/runner/actions
    if [[ -e "${runner_directory}/.runner" ]]; then
      echo "Runner is already registered; refusing to overwrite its credentials." >&2
      exit 1
    fi
    mkdir -p "${runner_directory}"
    cp -a --no-preserve=ownership /opt/actions-runner/. "${runner_directory}/"
    cd "${runner_directory}"
    # The short-lived registration token arrives on stdin, never in Docker's
    # stored environment, image layers or the repository.
    IFS= read -r runner_registration_token
    if [[ -z "${runner_registration_token}" ]]; then
      echo "Runner registration token is missing." >&2
      exit 1
    fi
    ./config.sh --unattended --url "${RUNNER_URL}" \
      --name "${RUNNER_NAME}" --labels minslab-gitlab-sync --work _work \
      --token "${runner_registration_token}"
    unset runner_registration_token
    ;;
  run)
    if [[ ! -f /home/runner/actions/.runner ]]; then
      echo "Register the runner before starting it." >&2
      exit 1
    fi
    git config --global pack.threads 2
    cd /home/runner/actions
    exec ./run.sh
    ;;
  *)
    exec "$@"
    ;;
esac
