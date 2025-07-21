#!/usr/bin/env python3

import os
import sys
import json
import datetime
import boto3

REGION = os.environ.get('AWS_REGION') or os.environ.get('AWS_DEFAULT_REGION') or 'us-east-1'
EVENT_BUS_NAME = os.environ.get('EVENT_BUS_NAME', 'default')

events = boto3.client('events', region_name=REGION)

runner_id = os.environ.get('RUNNER_ID') or os.uname().nodename


def update_status(status):
    ts = int(datetime.datetime.utcnow().timestamp())

    repo = os.environ.get('GITHUB_REPOSITORY')
    workflow = os.environ.get('GITHUB_WORKFLOW')
    job = os.environ.get('GITHUB_JOB')
    gh_run_id = os.environ.get('GITHUB_RUN_ID')
    run_key = f"{gh_run_id}:{job}" if gh_run_id and job else None

    detail = {
        'runner_id': runner_id,
        'status': status,
        'timestamp': ts,
    }
    if repo:
        detail['repository'] = repo
    if workflow:
        detail['workflow'] = workflow
    if job:
        detail['job'] = job
    if run_key:
        detail['workflow_job_id'] = run_key

    events.put_events(
        Entries=[{
            'Source': 'ecs-runner',
            'DetailType': 'runner-status',
            'Detail': json.dumps(detail),
            'EventBusName': EVENT_BUS_NAME,
        }]
    )


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print('usage: runner_status.py <status>', file=sys.stderr)
        sys.exit(1)
    update_status(sys.argv[1])
