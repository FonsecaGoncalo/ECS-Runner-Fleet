import os
import json
import base64
import hmac
import hashlib
import boto3
from boto3.dynamodb.conditions import Attr
import urllib.request
import time

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
LABEL_TASK_DEFINITIONS = json.loads(os.environ.get("LABEL_TASK_DEFINITIONS", "{}"))

ECR_REPOSITORY = os.environ.get("RUNNER_REPOSITORY_URL")
RUNNER_IMAGE_TAG = os.environ.get("RUNNER_IMAGE_TAG", "latest")
IMAGE_BUILD_PROJECT = os.environ.get("IMAGE_BUILD_PROJECT")

codebuild = boto3.client("codebuild") if IMAGE_BUILD_PROJECT else None
ecr = boto3.client("ecr") if ECR_REPOSITORY else None

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


def sanitize_image_label(label: str) -> str:
    return label.replace("/", "-").replace(":", "-")


def ensure_image_exists(base_image: str) -> str:
    if not ecr or not codebuild:
        raise Exception("Dynamic image build not configured")
    tag = f"{RUNNER_IMAGE_TAG}-{sanitize_image_label(base_image)}"
    repo_name = ECR_REPOSITORY.split("/")[-1]
    try:
        ecr.describe_images(repositoryName=repo_name, imageIds=[{"imageTag": tag}])
        print(f"Image {tag} already in repository")
    except ecr.exceptions.ImageNotFoundException:
        print(f"Building image for {base_image} as {tag}")
        build = codebuild.start_build(
            projectName=IMAGE_BUILD_PROJECT,
            environmentVariablesOverride=[
                {"name": "BASE_IMAGE", "value": base_image, "type": "PLAINTEXT"},
                {"name": "TARGET_TAG", "value": tag, "type": "PLAINTEXT"},
                {"name": "REPOSITORY", "value": repo_name, "type": "PLAINTEXT"},
            ],
        )
        build_id = build["build"]["id"]
        status = "IN_PROGRESS"
        while status == "IN_PROGRESS":
            time.sleep(10)
            resp = codebuild.batch_get_builds(ids=[build_id])
            status = resp["builds"][0]["buildStatus"]
            print(f"Build status: {status}")
        if status != "SUCCEEDED":
            raise Exception(f"Image build failed: {status}")
    return f"{ECR_REPOSITORY}:{tag}"


def register_temp_task_definition(image_uri: str, label: str) -> str:
    resp = ecs.describe_task_definition(taskDefinition=TASK_DEFINITION)
    td = resp["taskDefinition"]
    container = td["containerDefinitions"][0]
    container["image"] = image_uri
    for field in ["taskDefinitionArn", "revision", "status", "requiresAttributes", "compatibilities", "registeredAt", "registeredBy"]:
        td.pop(field, None)
    td["family"] = f"{td['family']}-{sanitize_image_label(label)}"
    new_td = ecs.register_task_definition(
        family=td["family"],
        networkMode=td["networkMode"],
        executionRoleArn=td.get("executionRoleArn"),
        taskRoleArn=td.get("taskRoleArn"),
        requiresCompatibilities=td.get("requiresCompatibilities"),
        cpu=str(td.get("cpu")),
        memory=str(td.get("memory")),
        containerDefinitions=[container],
    )
    return new_td["taskDefinition"]["taskDefinitionArn"]


def handle_status_event(detail):
    if isinstance(detail, str):
        try:
            detail = json.loads(detail)
        except json.JSONDecodeError:
            detail = {}
    status = detail.get("status")
    runner_id = detail.get("runner_id")
    ts = detail.get("timestamp", int(time.time()))
    run_key = detail.get("workflow_job_id")

    table = dynamodb.Table(RUNNER_TABLE)
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
                "repository": detail.get("repository"),
                "workflow": detail.get("workflow"),
                "job": detail.get("job"),
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
                print(f"Failed to update run record: {exc}")

    table.put_item(Item=state_item)


def lambda_handler(event, context):
    print("Received event:", json.dumps(event))

    if event.get("detail-type") == "runner-status":
        handle_status_event(event.get("detail"))
        return {"statusCode": 200, "body": "status updated"}

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
    task_def = TASK_DEFINITION
    for lbl in job_labels:
        if lbl in LABEL_TASK_DEFINITIONS:
            task_def = LABEL_TASK_DEFINITIONS[lbl]
            print(f"Using task definition for label {lbl}: {task_def}")
            break
    for lbl in job_labels:
        if lbl.startswith("image:"):
            base_image = lbl.split(":", 1)[1]
            try:
                image_uri = ensure_image_exists(base_image)
                task_def = register_temp_task_definition(image_uri, lbl)
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
        taskDefinition=task_def,
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
