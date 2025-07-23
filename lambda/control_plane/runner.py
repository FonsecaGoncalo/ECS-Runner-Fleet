import json
import os
import urllib.request

from botocore.exceptions import ClientError

import config
from image import sanitize_image_label


def get_runner_token(repo: str, pat: str) -> str:
    """Request a registration token for a repository runner."""
    url = (
        f"https://api.github.com/repos/{repo}/actions/"
        "runners/registration-token"
    )
    req = urllib.request.Request(
        url,
        method="POST",
        headers={
            "Authorization": f"token {pat}",
            "Accept": "application/vnd.github+json",
        },
    )
    with urllib.request.urlopen(req) as resp:
        data = json.load(resp)
    return data["token"]


def get_task_definition(image_uri: str, label: str | None = None):
    """Retrieve or register a task definition for the runner image."""
    try:
        family = "github-runner"
        task_def_name = f"{family}-{sanitize_image_label(label)}"
        print(f"Getting definition for {task_def_name}")
        resp = config.ecs.describe_task_definition(taskDefinition=task_def_name)
        print(f"Found {task_def_name}")
        return resp["taskDefinition"]["taskDefinitionArn"]
    except ClientError as e:
        if e.response["Error"]["Code"] == "ClientException":
            return register_task_definition(image_uri, label)
        raise


def register_task_definition(image_uri: str, label: str | None = None) -> str:
    """Register a new task definition for the runner image."""
    family = "github-runner"
    if label:
        family = f"{family}-{sanitize_image_label(label)}"

    print(f"Registering task {family}")

    container = {
        "name": "runner",
        "image": image_uri,
        "cpu": 1024,
        "memory": 2048,
        "essential": True,
        "environment": [
            {"name": "GITHUB_REPO", "value": config.GITHUB_REPO},
            {"name": "EVENT_BUS_NAME", "value": config.EVENT_BUS_NAME or ""},
        ],
        "logConfiguration": {
            "logDriver": "awslogs",
            "options": {
                "awslogs-group": config.LOG_GROUP_NAME,
                "awslogs-region": os.environ.get("AWS_REGION", "us-east-1"),
                "awslogs-stream-prefix": "runner",
            },
        },
    }

    resp = config.ecs.register_task_definition(
        family=family,
        networkMode="awsvpc",
        executionRoleArn=config.EXECUTION_ROLE_ARN,
        taskRoleArn=config.TASK_ROLE_ARN,
        requiresCompatibilities=["FARGATE"],
        cpu="1024",
        memory="2048",
        containerDefinitions=[container],
    )
    return resp["taskDefinition"]["taskDefinitionArn"]


def run_runner_task(
    image_uri: str,
    runner_labels: str,
    class_name: str | None = None,
    label: str | None = None,
    repo: str | None = None,
    pat: str | None = None,
) -> dict:
    """Run a GitHub Actions runner task via ECS.

    This helper fetches a registration token, ensures the task definition
    exists for the provided ``image_uri`` and then launches the task.
    """

    repo = repo or config.GITHUB_REPO
    pat = pat or config.GITHUB_PAT
    if not repo or not pat:
        raise RuntimeError("GITHUB_REPO and GITHUB_PAT must be configured")

    token = get_runner_token(repo, pat)
    task_def = get_task_definition(image_uri, label)
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

    sizes = config.get_class_sizes()
    if class_name and sizes and class_name in sizes:
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
    return response
