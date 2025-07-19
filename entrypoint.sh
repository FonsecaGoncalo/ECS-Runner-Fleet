#!/bin/bash

set -e

if [ -z "$RUNNER_REPOSITORY_URL" ] || [ -z "$RUNNER_TOKEN" ]; then
  echo "RUNNER_REPOSITORY_URL and RUNNER_TOKEN must be set"
  exit 1
fi

./config.sh --unattended \
    --url "$RUNNER_REPOSITORY_URL" \
    --token "$RUNNER_TOKEN" \
    --labels "${RUNNER_LABELS:-ecs-fargate}" \
    --name "${RUNNER_NAME:-fargate-runner}"

cleanup() {
    echo "Removing runner..."
    ./config.sh remove --unattended --token "$RUNNER_TOKEN"
}

trap 'cleanup; exit 130' INT
trap 'cleanup; exit 143' TERM

./run.sh & wait $!
