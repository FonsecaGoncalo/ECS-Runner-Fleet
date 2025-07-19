import os
import json
import base64
import hmac
import hashlib
import boto3
from boto3.dynamodb.conditions import Attr
import urllib.request

ecs = boto3.client("ecs")
dynamodb = boto3.resource("dynamodb")

CLUSTER = os.environ.get("CLUSTER", "runner-cluster")
TASK_DEFINITION = os.environ["TASK_DEFINITION"]
SUBNETS = os.environ.get("SUBNETS", "").split(",")
SECURITY_GROUPS = os.environ.get("SECURITY_GROUPS", "").split(",")
GITHUB_PAT = os.environ.get("GITHUB_PAT")
GITHUB_REPO = os.environ.get("GITHUB_REPO")
WEBHOOK_SECRET = os.environ.get("GITHUB_WEBHOOK_SECRET")
RUNNER_TABLE = os.environ.get("RUNNER_TABLE")


def get_runner_token(repo, pat):
    url = (
        f"https://api.github.com/repos/{repo}/actions/runners/registration-token"
    )
    req = urllib.request.Request(
        url,
        method="POST",
        headers={"Authorization": f"token {pat}", "Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(req) as resp:
        data = json.load(resp)
    return data["token"]


def lambda_handler(event, context):
    print("Received event:", json.dumps(event))

    body = event.get("body")
    if body is None:
        print("No body in event")
        return {"statusCode": 400, "body": "no event body"}

    if event.get("isBase64Encoded"):
        body_bytes = base64.b64decode(body)
        body_str = body_bytes.decode()
    else:
        body_bytes = body.encode()
        body_str = body

    signature = event.get("headers", {}).get("x-hub-signature-256")
    if not signature:
        print("Missing signature header")
        return {"statusCode": 401, "body": "missing signature"}

    expected = "sha256=" + hmac.new(
        WEBHOOK_SECRET.encode(), body_bytes, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(signature, expected):
        print("Invalid webhook signature")
        return {"statusCode": 401, "body": "invalid signature"}
    try:
        payload = json.loads(body_str)
    except json.JSONDecodeError:
        print("Invalid JSON payload")
        return {"statusCode": 400, "body": "invalid json"}

    action = payload.get("action")
    if action != "queued" or "workflow_job" not in payload:
        print(f"Ignoring action: {action}")
        return {"statusCode": 200, "body": "ignored"}

    if RUNNER_TABLE:
        table = dynamodb.Table(RUNNER_TABLE)
        resp = table.scan(FilterExpression=Attr("status").eq("idle"))
        if resp.get("Items"):
            print("Idle runner available, skipping new task")
            return {"statusCode": 200, "body": "runner available"}

    token = get_runner_token(GITHUB_REPO, GITHUB_PAT)
    response = ecs.run_task(
        cluster=CLUSTER,
        launchType="FARGATE",
        taskDefinition=TASK_DEFINITION,
        count=1,
        enableExecuteCommand=True,
        overrides={
            "containerOverrides": [
                {
                    "name": "runner",
                    "environment": [
                        {
                            "name": "RUNNER_REPOSITORY_URL",
                            "value": f"https://github.com/{GITHUB_REPO}",
                        },
                        {"name": "RUNNER_TOKEN", "value": token},
                        {"name": "RUNNER_LABELS", "value": "default-runner"},
                        {"name": "RUNNER_NAME", "value": "my-runner"},
                        {"name": "RUNNER_TABLE", "value": RUNNER_TABLE or ""},
                    ],
                }
            ]
        },
        networkConfiguration={
            "awsvpcConfiguration": {
                "subnets": SUBNETS,
                "securityGroups": SECURITY_GROUPS,
                "assignPublicIp": "ENABLED",
            }
        },
    )
    print("Run task response:", response)
    return {"statusCode": 200, "body": "task started"}
