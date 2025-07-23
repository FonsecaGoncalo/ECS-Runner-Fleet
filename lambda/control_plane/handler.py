import base64
import hashlib
import hmac
import json

import config
from image import ensure_image_exists, get_task_definition
from status import handle_status_event
from github import get_runner_token


def lambda_handler(event, context):
    """Entry point for the runner control plane Lambda."""
    print("Received event:", json.dumps(event))

    sizes = config.get_class_sizes()
    if sizes:
        print("Available class sizes:", sizes)

    if event.get("detail-type") == "runner-status":
        handle_status_event(event.get("detail"))
        return {"statusCode": 200, "body": "status updated"}

    if event.get("detail-type") == "image-build":
        detail = event.get("detail", {})
        build_id = detail.get("build_id")
        image_uri = detail.get("image_uri")
        status = detail.get("status")

        table = config.dynamodb.Table(config.RUNNER_TABLE)
        if not build_id:
            return {"statusCode": 400, "body": "missing build id"}
        resp = table.get_item(Key={"runner_id": build_id, "item_id": "state"})
        item = resp.get("Item")
        if not item:
            print(f"No entry for build {build_id}")
            return {"statusCode": 200, "body": "no entry"}

        if status != "SUCCEEDED":
            table.update_item(
                Key={"runner_id": build_id, "item_id": "state"},
                UpdateExpression="SET #s = :failed",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={":failed": "image failed"},
            )
            return {"statusCode": 200, "body": "build failed"}

        runner_labels = item.get("runner_labels", "default-runner")
        class_name = item.get("class_name")
        image_label = f"image:{item.get('image_tag')}"

        task_def = get_task_definition(image_uri, image_label)
        token = get_runner_token(config.GITHUB_REPO, config.GITHUB_PAT)

        overrides = {
            "containerOverrides": [
                {
                    "name": "runner",
                    "environment": [
                        {
                            "name": "RUNNER_REPOSITORY_URL",
                            "value": (
                                f"https://github.com/{config.GITHUB_REPO}"
                            ),
                        },
                        {"name": "RUNNER_TOKEN", "value": token},
                        {"name": "RUNNER_LABELS", "value": runner_labels},
                        {"name": "RUNNER_NAME", "value": "my-runner"},
                        {
                            "name": "RUNNER_TABLE",
                            "value": config.RUNNER_TABLE or "",
                        },
                    ],
                }
            ]
        }

        if class_name and sizes and class_name in sizes:
            cpu = sizes[class_name].get("cpu")
            memory = sizes[class_name].get("memory")
            overrides["cpu"] = str(cpu)
            overrides["memory"] = str(memory)
            overrides["containerOverrides"][0]["cpu"] = cpu
            overrides["containerOverrides"][0]["memory"] = memory

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

        table.delete_item(Key={"runner_id": build_id, "item_id": "state"})
        return {"statusCode": 200, "body": "runner started"}

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

    token = get_runner_token(config.GITHUB_REPO, config.GITHUB_PAT)

    job = payload.get("workflow_job", {})
    job_labels = job.get("labels", [])
    runner_labels = ",".join(job_labels) if job_labels else "default-runner"

    base_image = None
    class_name = None
    for lbl in job_labels:
        if lbl.startswith("image:"):
            base_image = lbl.split(":", 1)[1]
        elif lbl.startswith("class:"):
            class_name = lbl.split(":", 1)[1]

    task_def = None
    if base_image:
        try:
            image_uri = ensure_image_exists(
                base_image,
                runner_labels,
                class_name,
            )
            if image_uri is None:
                print("Image build triggered, exiting")
                return {"statusCode": 202, "body": "image build"}
            task_def = get_task_definition(
                image_uri,
                f"image:{base_image}",
            )
            print(f"Using dynamic image {image_uri}")
        except Exception as exc:
            print(f"Failed to prepare image {base_image}: {exc}")
            return {"statusCode": 500, "body": "image build failed"}
    else:
        image_uri = f"{config.ECR_REPOSITORY}:{config.RUNNER_IMAGE_TAG}"
        task_def = get_task_definition(image_uri)

    overrides = {
        "containerOverrides": [
            {
                "name": "runner",
                "environment": [
                    {
                        "name": "RUNNER_REPOSITORY_URL",
                        "value": (
                            f"https://github.com/{config.GITHUB_REPO}"
                        ),
                    },
                    {"name": "RUNNER_TOKEN", "value": token},
                    {"name": "RUNNER_LABELS", "value": runner_labels},
                    {"name": "RUNNER_NAME", "value": "my-runner"},
                    {
                        "name": "RUNNER_TABLE",
                        "value": config.RUNNER_TABLE or "",
                    },
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
