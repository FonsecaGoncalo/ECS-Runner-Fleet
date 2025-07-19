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

# unique id for this runner
export RUNNER_ID="${RUNNER_NAME:-fargate-runner}-$(hostname)"

# mark runner initially idle in DynamoDB
[ -n "$RUNNER_TABLE" ] && /home/runner/runner_status.py idle || true

cleanup() {
    echo "Removing runner..."
    [ -n "$RUNNER_TABLE" ] && /home/runner/runner_status.py offline || true
    ./config.sh remove --unattended --token "$RUNNER_TOKEN"
}

trap 'cleanup; exit 130' INT
trap 'cleanup; exit 143' TERM

./run.sh & wait $!
