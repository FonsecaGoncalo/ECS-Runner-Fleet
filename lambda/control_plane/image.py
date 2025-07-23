import os
import re

from botocore.exceptions import ClientError

import config


def sanitize_image_label(label: str) -> str:
    """Sanitize image label for use in ECR tags and task definitions."""
    # Convert any character that isn't allowed in ECR tags or ECS family names
    # into a hyphen.  Valid characters are letters, numbers, ``_`` and ``-``
    sanitized = re.sub(r"[^a-zA-Z0-9_-]", "-", label)
    return sanitized


def ensure_image_exists(
        base_image: str,
        runner_labels: str | None = None,
        class_name: str | None = None,
) -> str | None:
    """Ensure a runner image exists for the requested base image.

    The incoming ``base_image`` might contain characters such as ``/`` or ``:``
    which are not valid in ECR tags.  We therefore sanitize it before using it
    as an image tag or passing it to CodeBuild.  If the image is not present it
    is built asynchronously using CodeBuild and a DynamoDB record is created
    with ``status`` set to ``image creating``.
    """
    if not config.ecr or not config.codebuild:
        raise Exception("Dynamic image build not configured")

    repo_name = config.ECR_REPOSITORY.split("/")[-1]
    tag = sanitize_image_label(base_image)
    try:
        config.ecr.describe_images(
            repositoryName=repo_name, imageIds=[{"imageTag": tag}]
        )
        print(f"Image {tag} already in repository")
        return f"{config.ECR_REPOSITORY}:{tag}"
    except config.ecr.exceptions.ImageNotFoundException:
        if runner_labels is None:
            # No context to request a build
            raise Exception("Image not found and no build context provided")

        print(f"Building image for {base_image}")
        build = config.codebuild.start_build(
            projectName=config.IMAGE_BUILD_PROJECT,
            environmentVariablesOverride=[
                {"name": "BASE_IMAGE", "value": base_image, "type": "PLAINTEXT"},
                {"name": "TAG", "value": tag, "type": "PLAINTEXT"},
                {
                    "name": "REPOSITORY",
                    "value": repo_name,
                    "type": "PLAINTEXT",
                },
                {
                    "name": "EVENT_BUS_NAME",
                    "value": config.EVENT_BUS_NAME,
                    "type": "PLAINTEXT",
                },
            ],
        )
        build_id = build["build"]["id"]

        table = config.dynamodb.Table(config.RUNNER_TABLE)
        item = {
            "runner_id": build_id,
            "item_id": "state",
            "status": "image creating",
            "image_tag": tag,
            "runner_labels": runner_labels,
        }
        if class_name:
            item["class_name"] = class_name
        table.put_item(Item=item)

        print(f"Image build {build_id} started")
        return None


def get_task_definition(image_uri: str, label: str | None = None):
    try:
        family = "github-runner"
        task_def_name = f"{family}-{sanitize_image_label(label)}"
        print(f"Getting definition for {task_def_name}")
        resp = config.ecs.describe_task_definition(taskDefinition=task_def_name)
        print(f"Found {task_def_name}")
        return resp["taskDefinition"]["taskDefinitionArn"]
    except ClientError as e:
        if e.response['Error']['Code'] == 'ClientException':
            return register_task_definition(image_uri, label)
        else:
            raise


def register_task_definition(image_uri: str, label: str | None = None) -> str:
    """Register a task definition for the runner image."""
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
            {
                "name": "ACTIONS_RUNNER_HOOK_JOB_STARTED",
                "value": "/home/runner/job_started.sh",
            },
            {
                "name": "ACTIONS_RUNNER_HOOK_JOB_COMPLETED",
                "value": "/home/runner/job_completed.sh",
            },
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
