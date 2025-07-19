import os
import json
import boto3

ecs = boto3.client("ecs")

CLUSTER = os.environ.get("CLUSTER", "runner-cluster")
TASK_DEFINITION = os.environ["TASK_DEFINITION"]
SUBNETS = os.environ.get("SUBNETS", "").split(",")
SECURITY_GROUPS = os.environ.get("SECURITY_GROUPS", "").split(",")


def lambda_handler(event, context):
    print("Received event:", json.dumps(event))
    response = ecs.run_task(
        cluster=CLUSTER,
        launchType="FARGATE",
        taskDefinition=TASK_DEFINITION,
        count=1,
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
