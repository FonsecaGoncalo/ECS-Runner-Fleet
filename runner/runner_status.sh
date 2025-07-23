#!/bin/sh
set -e

if [ "$#" -ne 1 ]; then
    echo "usage: runner_status.sh <status>" >&2
    exit 1
fi

STATUS=$1
REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"
EVENT_BUS_NAME="${EVENT_BUS_NAME:-default}"
RUNNER_ID="${RUNNER_ID:-$(hostname)}"
TIMESTAMP=$(date -u +%s)

detail=$(jq -n \
    --arg runner_id "$RUNNER_ID" \
    --arg status "$STATUS" \
    --arg ts "$TIMESTAMP" \
    --arg repo "${GITHUB_REPOSITORY:-}" \
    --arg workflow "${GITHUB_WORKFLOW:-}" \
    --arg job "${GITHUB_JOB:-}" \
    --arg run_id "${GITHUB_RUN_ID:-}" \
    '{runner_id:$runner_id,status:$status,timestamp:($ts|tonumber)} +
     (if $repo != "" then {repository:$repo} else {} end) +
     (if $workflow != "" then {workflow:$workflow} else {} end) +
     (if $job != "" then {job:$job} else {} end) +
     (if $run_id != "" and $job != "" then {workflow_job_id:($run_id+":"+$job)} else {} end)' | jq -c '.' )

entries=$(jq -n --arg detail "$detail" --arg eb "$EVENT_BUS_NAME" '[{Source:"ecs-runner",DetailType:"runner-status",Detail:$detail,EventBusName:$eb}]')

aws events put-events --region "$REGION" --entries "$entries" >/dev/null