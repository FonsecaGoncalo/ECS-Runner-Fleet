import os
import re

import config
from db import put_item


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

        item = {
            "runner_id": build_id,
            "item_id": "state",
            "status": "image creating",
            "image_tag": tag,
            "runner_labels": runner_labels,
        }
        if class_name:
            item["class_name"] = class_name
        put_item(item)

        print(f"Image build {build_id} started")
        return None
