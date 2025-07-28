from __future__ import annotations

import json
import os
import urllib.request
from typing import Any, Dict, Optional

from botocore.exceptions import ClientError

from ..config import Settings, client, get_class_sizes
from .images import sanitize_image_label


def get_runner_token(settings: Settings) -> str:
    url = (
        f"https://api.github.com/repos/{settings.github_repo}/actions/"
        "runners/registration-token"
    )
    req = urllib.request.Request(
        url,
        method="POST",
        headers={
            "Authorization": f"token {settings.github_pat}",
            "Accept": "application/vnd.github+json",
        },
    )
    with urllib.request.urlopen(req) as resp:
        data = json.load(resp)
    return data["token"]


def get_task_definition(
    settings: Settings, image_uri: str, label: Optional[str] = None
) -> str:
    ecs = client("ecs")
    family = "github-runner"
    if label:
        family = f"{family}-{sanitize_image_label(label)}"
    try:
        resp = ecs.describe_task_definition(taskDefinition=family)
        return resp["taskDefinition"]["taskDefinitionArn"]
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "ClientException":
            raise
    container = {
        "name": "runner",
        "image": image_uri,
        "cpu": 1024,
        "memory": 2048,
        "essential": True,
        "environment": [
            {"name": "GITHUB_REPO", "value": settings.github_repo},
            {"name": "EVENT_BUS_NAME", "value": settings.event_bus_name or ""},
        ],
        "logConfiguration": {
            "logDriver": "awslogs",
            "options": {
                "awslogs-group": settings.log_group_name,
                "awslogs-region": os.environ.get("AWS_REGION", "us-east-1"),
                "awslogs-stream-prefix": "runner",
            },
        },
    }
    resp = ecs.register_task_definition(
        family=family,
        networkMode="awsvpc",
        executionRoleArn=settings.execution_role_arn,
        taskRoleArn=settings.task_role_arn,
        requiresCompatibilities=["FARGATE"],
        cpu="1024",
        memory="2048",
        containerDefinitions=[container],
    )
    return resp["taskDefinition"]["taskDefinitionArn"]


def run_runner_task(
    settings: Settings,
    image_uri: str,
    runner_labels: str,
    class_name: Optional[str] = None,
    label: Optional[str] = None,
) -> Dict[str, Any]:
    ecs = client("ecs")
    token = get_runner_token(settings)
    task_def = get_task_definition(settings, image_uri, label)
    overrides: Dict[str, Any] = {
        "containerOverrides": [
            {
                "name": "runner",
                "environment": [
                    {
                        "name": "RUNNER_REPOSITORY_URL",
                        "value": f"https://github.com/{settings.github_repo}",
                    },
                    {"name": "RUNNER_TOKEN", "value": token},
                    {"name": "RUNNER_LABELS", "value": runner_labels},
                    {"name": "RUNNER_NAME", "value": "runner"},
                    {"name": "RUNNER_TABLE", "value": settings.runner_table},
                ],
            }
        ]
    }
    sizes = get_class_sizes(settings)
    if class_name and class_name in sizes:
        cpu = sizes[class_name].get("cpu")
        memory = sizes[class_name].get("memory")
        overrides["cpu"] = str(cpu)
        overrides["memory"] = str(memory)
        overrides["containerOverrides"][0]["cpu"] = cpu
        overrides["containerOverrides"][0]["memory"] = memory
    response = ecs.run_task(
        cluster=settings.cluster,
        launchType="FARGATE",
        taskDefinition=task_def,
        count=1,
        enableExecuteCommand=True,
        overrides=overrides,
        networkConfiguration={
            "awsvpcConfiguration": {
                "subnets": settings.subnets,
                "securityGroups": settings.security_groups,
                "assignPublicIp": "ENABLED",
            }
        },
    )
    return response
