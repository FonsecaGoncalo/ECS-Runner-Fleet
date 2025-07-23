#!/bin/sh
/home/runner/runner_status.sh completed


if [ -n "$ECS_CONTAINER_METADATA_URI_V4" ]; then
    meta=$(curl -s "$ECS_CONTAINER_METADATA_URI_V4/task")
    cluster=$(echo "$meta" | jq -r '.Cluster')
    task=$(echo "$meta" | jq -r '.TaskARN')
    region="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"
        aws ecs stop-task --cluster "$cluster" --task "$task" --region "$region" \
            --reason "runner job completed" >/dev/null
fi