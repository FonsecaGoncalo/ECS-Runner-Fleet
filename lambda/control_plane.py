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
ssm = boto3.client("ssm")

CLUSTER = os.environ.get("CLUSTER", "runner-cluster")
TASK_DEFINITION = os.environ["TASK_DEFINITION"]
SUBNETS = os.environ.get("SUBNETS", "").split(",")
SECURITY_GROUPS = os.environ.get("SECURITY_GROUPS", "").split(",")
GITHUB_PAT = os.environ.get("GITHUB_PAT")
GITHUB_REPO = os.environ.get("GITHUB_REPO")
WEBHOOK_SECRET = os.environ.get("GITHUB_WEBHOOK_SECRET")
RUNNER_TABLE = os.environ.get("RUNNER_TABLE")
CLASS_SIZES_PARAM = os.environ.get("CLASS_SIZES_PARAM")

_class_sizes = None

def get_class_sizes():
    global _class_sizes
    if _class_sizes is not None:
        return _class_sizes
    if not CLASS_SIZES_PARAM:
        _class_sizes = {}
        return _class_sizes
    try:
        resp = ssm.get_parameter(Name=CLASS_SIZES_PARAM)
        _class_sizes = json.loads(resp["Parameter"]["Value"])
    except Exception as exc:
        print(f"Failed to load class sizes: {exc}")
        _class_sizes = {}
    return _class_sizes


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

    sizes = get_class_sizes()
    if sizes:
        print("Available class sizes:", sizes)

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

    job = payload.get("workflow_job", {})
    job_labels = job.get("labels", [])
    runner_labels = ",".join(job_labels) if job_labels else "default-runner"
    class_name = None
    for lbl in job_labels:
        if lbl.startswith("class:"):
            class_name = lbl.split(":", 1)[1]
            break

    overrides = {
        "containerOverrides": [
            {
                "name": "runner",
                "environment": [
                    {
                        "name": "RUNNER_REPOSITORY_URL",
                        "value": f"https://github.com/{GITHUB_REPO}",
                    },
                    {"name": "RUNNER_TOKEN", "value": token},
                    {"name": "RUNNER_LABELS", "value": runner_labels},
                    {"name": "RUNNER_NAME", "value": "my-runner"},
                    {"name": "RUNNER_TABLE", "value": RUNNER_TABLE or ""},
                ],
            }
        ]
    }

    if class_name and class_name in sizes:
        cpu = sizes[class_name].get("cpu")
        memory = sizes[class_name].get("memory")
        overrides["cpu"] = str(cpu)
        overrides["memory"] = str(memory)
        overrides["containerOverrides"][0]["cpu"] = cpu
        overrides["containerOverrides"][0]["memory"] = memory
        print(f"Using class {class_name}: cpu={cpu} memory={memory}")

    response = ecs.run_task(
        cluster=CLUSTER,
        launchType="FARGATE",
        taskDefinition=TASK_DEFINITION,
        count=1,
        enableExecuteCommand=True,
        overrides=overrides,
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
