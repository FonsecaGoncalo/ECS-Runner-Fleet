import os
import json
import boto3
import urllib.request

ecs = boto3.client("ecs")

CLUSTER = os.environ.get("CLUSTER", "runner-cluster")
TASK_DEFINITION = os.environ["TASK_DEFINITION"]
SUBNETS = os.environ.get("SUBNETS", "").split(",")
SECURITY_GROUPS = os.environ.get("SECURITY_GROUPS", "").split(",")
GITHUB_PAT = os.environ.get("GITHUB_PAT")
GITHUB_REPO = os.environ.get("GITHUB_REPO")


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


def lambda_handler(event, context):
    print("Received event:", json.dumps(event))
    token = get_runner_token(GITHUB_REPO, GITHUB_PAT)
    response = ecs.run_task(
        cluster=CLUSTER,
        launchType="FARGATE",
        taskDefinition=TASK_DEFINITION,
        count=1,
        overrides={
            "containerOverrides": [
                {
                    "name": "runner",
                    "environment": [
                        {
                            "name": "RUNNER_REPOSITORY_URL",
                            "value": f"https://github.com/{GITHUB_REPO}",
                        },
                        {"name": "RUNNER_TOKEN", "value": token},
                        {"name": "RUNNER_LABELS", "value": "default-runner"},
                        {"name": "RUNNER_NAME", "value": "my-runner"},
                    ],
                }
            ]
        },
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
