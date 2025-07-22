import os
import time

import config


def sanitize_image_label(label: str) -> str:
    """Sanitize image label for use in ECR tags."""
    return label.replace("/", "-").replace(":", "-")


def ensure_image_exists(base_image: str) -> str:
    """Ensure a runner image exists for the requested base image.

    The incoming ``base_image`` might contain characters such as ``/`` or ``:``
    which are not valid in ECR tags.  We therefore sanitize it before using it
    as an image tag or passing it to CodeBuild.
    """
    if not config.ecr or not config.codebuild:
        raise Exception("Dynamic image build not configured")
    repo_name = config.ECR_REPOSITORY.split("/")[-1]
    tag = sanitize_image_label(base_image)
    try:
        config.ecr.describe_images(repositoryName=repo_name, imageIds=[{"imageTag": tag}])
        print(f"Image {tag} already in repository")
    except config.ecr.exceptions.ImageNotFoundException:
        print(f"Building image for {base_image}")
        build = config.codebuild.start_build(
            projectName=config.IMAGE_BUILD_PROJECT,
            environmentVariablesOverride=[
                {"name": "BASE_IMAGE", "value": tag, "type": "PLAINTEXT"},
                {"name": "REPOSITORY", "value": repo_name, "type": "PLAINTEXT"},
            ],
        )
        build_id = build["build"]["id"]
        status = "IN_PROGRESS"
        while status == "IN_PROGRESS":
            time.sleep(10)
            resp = config.codebuild.batch_get_builds(ids=[build_id])
            status = resp["builds"][0]["buildStatus"]
            print(f"Build status: {status}")
        if status != "SUCCEEDED":
            raise Exception(f"Image build failed: {status}")
    return f"{config.ECR_REPOSITORY}:{tag}"


def register_task_definition(image_uri: str, label: str | None = None) -> str:
    """Register a task definition for the runner image."""
    family = "github-runner"
    if label:
        family = f"{family}-{sanitize_image_label(label)}"

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
