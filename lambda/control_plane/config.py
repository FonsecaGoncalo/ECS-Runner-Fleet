import json
import os

import boto3

# boto3 clients
ecs = boto3.client("ecs")
dynamodb = boto3.resource("dynamodb")
ssm = boto3.client("ssm")

# environment configuration
CLUSTER = os.environ.get("CLUSTER", "runner-cluster")
SUBNETS = os.environ.get("SUBNETS", "").split(",")
SECURITY_GROUPS = os.environ.get("SECURITY_GROUPS", "").split(",")
GITHUB_PAT = os.environ.get("GITHUB_PAT")
GITHUB_REPO = os.environ.get("GITHUB_REPO")
WEBHOOK_SECRET = os.environ.get("GITHUB_WEBHOOK_SECRET")
RUNNER_TABLE = os.environ.get("RUNNER_TABLE")
CLASS_SIZES_PARAM = os.environ.get("CLASS_SIZES_PARAM")
EXECUTION_ROLE_ARN = os.environ.get("EXECUTION_ROLE_ARN")
TASK_ROLE_ARN = os.environ.get("TASK_ROLE_ARN")
LOG_GROUP_NAME = os.environ.get("LOG_GROUP_NAME")
EVENT_BUS_NAME = os.environ.get("EVENT_BUS_NAME")

ECR_REPOSITORY = os.environ.get("RUNNER_REPOSITORY_URL")
RUNNER_IMAGE_TAG = os.environ.get("RUNNER_IMAGE_TAG", "latest")
IMAGE_BUILD_PROJECT = os.environ.get("IMAGE_BUILD_PROJECT")

codebuild = boto3.client("codebuild") if IMAGE_BUILD_PROJECT else None
ecr = boto3.client("ecr") if ECR_REPOSITORY else None

_class_sizes = None

def get_class_sizes():
    """Return cached runner class size definitions."""
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
