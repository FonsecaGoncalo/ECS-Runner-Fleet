import time

from . import config


def sanitize_image_label(label: str) -> str:
    """Sanitize image label for use in ECR tags."""
    return label.replace("/", "-").replace(":", "-")


def ensure_image_exists(base_image: str) -> str:
    """Ensure a runner image exists for the requested base image."""
    if not config.ecr or not config.codebuild:
        raise Exception("Dynamic image build not configured")
    tag = f"{config.RUNNER_IMAGE_TAG}-{sanitize_image_label(base_image)}"
    repo_name = config.ECR_REPOSITORY.split("/")[-1]
    try:
        config.ecr.describe_images(repositoryName=repo_name, imageIds=[{"imageTag": tag}])
        print(f"Image {tag} already in repository")
    except config.ecr.exceptions.ImageNotFoundException:
        print(f"Building image for {base_image} as {tag}")
        build = config.codebuild.start_build(
            projectName=config.IMAGE_BUILD_PROJECT,
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
            resp = config.codebuild.batch_get_builds(ids=[build_id])
            status = resp["builds"][0]["buildStatus"]
            print(f"Build status: {status}")
        if status != "SUCCEEDED":
            raise Exception(f"Image build failed: {status}")
    return f"{config.ECR_REPOSITORY}:{tag}"


def register_temp_task_definition(image_uri: str, label: str) -> str:
    """Register a temporary task definition using the provided image."""
    resp = config.ecs.describe_task_definition(taskDefinition=config.TASK_DEFINITION)
    td = resp["taskDefinition"]
    container = td["containerDefinitions"][0]
    container["image"] = image_uri
    for field in [
        "taskDefinitionArn",
        "revision",
        "status",
        "requiresAttributes",
        "compatibilities",
        "registeredAt",
        "registeredBy",
    ]:
        td.pop(field, None)
    td["family"] = f"{td['family']}-{sanitize_image_label(label)}"
    new_td = config.ecs.register_task_definition(
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
