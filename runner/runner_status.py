#!/usr/bin/env python3

import os
import sys
import datetime
import boto3

TABLE_NAME = os.environ.get("RUNNER_TABLE")
REGION = os.environ.get('AWS_REGION') or os.environ.get('AWS_DEFAULT_REGION') or 'us-east-1'

if not TABLE_NAME:
    print('RUNNER_TABLE environment variable required', file=sys.stderr)
    sys.exit(1)

db = boto3.resource("dynamodb", region_name=REGION)
table = db.Table(TABLE_NAME)

runner_id = os.environ.get('RUNNER_ID') or os.uname().nodename


def update_status(status):
    ts = int(datetime.datetime.utcnow().timestamp())

    repo = os.environ.get("GITHUB_REPOSITORY")
    workflow = os.environ.get("GITHUB_WORKFLOW")
    job = os.environ.get("GITHUB_JOB")
    gh_run_id = os.environ.get("GITHUB_RUN_ID")
    run_key = f"{gh_run_id}:{job}" if gh_run_id and job else None

    state_item = {
        "runner_id": runner_id,
        "item_id": "state",
        "status": status,
        "timestamp": ts,
    }
    if run_key:
        state_item["workflow_job_id"] = run_key

    if status == "running" and run_key:
        state_item["started_at"] = ts
        table.put_item(
            Item={
                "runner_id": runner_id,
                "item_id": f"run#{run_key}",
                "run_id": run_key,
                "repository": repo,
                "workflow": workflow,
                "job": job,
                "started_at": ts,
            }
        )
    elif status in ("idle", "offline"):
        state_item["completed_at"] = ts
        if run_key:
            try:
                table.update_item(
                    Key={"runner_id": runner_id, "item_id": f"run#{run_key}"},
                    UpdateExpression="SET completed_at = :ts",
                    ExpressionAttributeValues={":ts": ts},
                )
            except Exception as exc:
                print(f"Failed to update run record: {exc}", file=sys.stderr)

    table.put_item(Item=state_item)

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print('usage: runner_status.py <status>', file=sys.stderr)
        sys.exit(1)
    update_status(sys.argv[1])
