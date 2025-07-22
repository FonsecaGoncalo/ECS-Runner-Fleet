import base64
import hashlib
import hmac
import json

from boto3.dynamodb.conditions import Attr

import config
from image import ensure_image_exists, register_task_definition
from status import handle_status_event
from github import get_runner_token


def lambda_handler(event, context):
    """Entry point for the runner control plane Lambda."""
    print("Received event:", json.dumps(event))

    if event.get("detail-type") == "runner-status":
        handle_status_event(event.get("detail"))
        return {"statusCode": 200, "body": "status updated"}

    sizes = config.get_class_sizes()
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
        config.WEBHOOK_SECRET.encode(), body_bytes, hashlib.sha256
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

    # if config.RUNNER_TABLE:
    #     table = config.dynamodb.Table(config.RUNNER_TABLE)
    #     resp = table.scan(FilterExpression=Attr("status").eq("idle"))
    #     if resp.get("Items"):
    #         print("Idle runner available, skipping new task")
    #         return {"statusCode": 200, "body": "runner available"}

    token = get_runner_token(config.GITHUB_REPO, config.GITHUB_PAT)

    job = payload.get("workflow_job", {})
    job_labels = job.get("labels", [])
    runner_labels = ",".join(job_labels) if job_labels else "default-runner"
    # image_uri = f"{config.ECR_REPOSITORY}:{config.RUNNER_IMAGE_TAG}"
    # task_def = register_task_definition(image_uri)
    print(f"Job labels: {runner_labels}")
    for lbl in job_labels:
        if lbl.startswith("image:"):
            base_image = lbl.split(":", 1)[1]
            try:
                image_uri = ensure_image_exists(base_image)
                task_def = register_task_definition(image_uri, lbl)
                print(f"Using dynamic image {image_uri}")
            except Exception as exc:
                print(f"Failed to prepare image {base_image}: {exc}")
            break
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
                        "value": f"https://github.com/{config.GITHUB_REPO}",
                    },
                    {"name": "RUNNER_TOKEN", "value": token},
                    {"name": "RUNNER_LABELS", "value": runner_labels},
                    {"name": "RUNNER_NAME", "value": "my-runner"},
                    {"name": "RUNNER_TABLE", "value": config.RUNNER_TABLE or ""},
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

    response = config.ecs.run_task(
        cluster=config.CLUSTER,
        launchType="FARGATE",
        taskDefinition=task_def,
        count=1,
        enableExecuteCommand=True,
        overrides=overrides,
        networkConfiguration={
            "awsvpcConfiguration": {
                "subnets": config.SUBNETS,
                "securityGroups": config.SECURITY_GROUPS,
                "assignPublicIp": "ENABLED",
            }
        },
    )
    print("Run task response:", response)
    return {"statusCode": 200, "body": "task started"}
