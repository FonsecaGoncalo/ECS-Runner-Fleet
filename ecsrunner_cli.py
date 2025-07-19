"""Command line tool to manage ECS-based GitHub Actions runners."""

import json
import os
import subprocess

import boto3
import click
from botocore.exceptions import BotoCoreError, ClientError


# Utilities ---------------------------------------------------------------

def _get_table():
    """Return DynamoDB table for runner state."""
    table_name = os.environ.get("RUNNER_STATE_TABLE")
    if not table_name:
        raise click.ClickException("RUNNER_STATE_TABLE environment variable is not set")
    dynamodb = boto3.resource("dynamodb")
    return dynamodb.Table(table_name)


def _ecs_client():
    """Return boto3 ECS client."""
    return boto3.client("ecs")


# Main CLI group ---------------------------------------------------------

@click.group()
def cli():
    """Manage GitHub Actions runners on ECS."""
    pass


# Runner commands --------------------------------------------------------

@cli.group()
def runners():
    """Commands related to individual runner tasks."""
    pass


@runners.command("list")
def list_runners():
    """List all runners and their statuses."""
    table = _get_table()
    items = []
    try:
        resp = table.scan()
        items.extend(resp.get("Items", []))
        while resp.get("LastEvaluatedKey"):
            resp = table.scan(ExclusiveStartKey=resp["LastEvaluatedKey"])
            items.extend(resp.get("Items", []))
    except ClientError as e:
        raise click.ClickException(str(e))

    click.echo(json.dumps(items, indent=2, default=str))


@runners.command("details")
@click.argument("runner_id")
def runner_details(runner_id):
    """Show details for a specific runner."""
    table = _get_table()
    try:
        resp = table.get_item(Key={"runner_id": runner_id})
    except ClientError as e:
        raise click.ClickException(str(e))

    item = resp.get("Item")
    if not item:
        raise click.ClickException("Runner not found")
    click.echo(json.dumps(item, indent=2, default=str))


@runners.command("terminate")
@click.argument("cluster_name")
@click.argument("task_arn")
def terminate_runner(cluster_name, task_arn):
    """Terminate a runner ECS task."""
    ecs = _ecs_client()
    try:
        ecs.stop_task(cluster=cluster_name, task=task_arn, reason="Stopped via ecsrunner-cli")
    except ClientError as e:
        raise click.ClickException(str(e))
    click.echo("Termination initiated")


@runners.command("idle")
@click.argument("runner_id")
def mark_idle(runner_id):
    """Mark runner as idle in DynamoDB."""
    table = _get_table()
    try:
        table.update_item(
            Key={"runner_id": runner_id},
            UpdateExpression="SET #s = :idle REMOVE workflow_job_id, started_at, completed_at",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":idle": "idle"},
        )
    except ClientError as e:
        raise click.ClickException(str(e))
    click.echo("Runner state updated to idle")


@runners.command("exec")
@click.argument("cluster_name")
@click.argument("task_id")
@click.option("--container", "container_name", help="Container name inside the task")
@click.option("--cmd", default="/bin/bash", show_default=True, help="Command to execute")
def exec_runner(cluster_name, task_id, container_name, cmd):
    """Open an interactive shell into a running ECS task."""
    command = [
        "aws",
        "ecs",
        "execute-command",
        "--cluster",
        cluster_name,
        "--task",
        task_id,
        "--command",
        cmd,
        "--interactive",
    ]
    if container_name:
        command.extend(["--container", container_name])

    try:
        subprocess.run(command, check=True)
    except subprocess.CalledProcessError as exc:
        raise click.ClickException(f"Failed to exec into task: {exc}")


# Cluster commands -------------------------------------------------------

@cli.group()
def cluster():
    """Cluster level commands."""
    pass


@cluster.command("status")
@click.argument("cluster_name")
def cluster_status(cluster_name):
    """Show ECS cluster task status."""
    ecs = _ecs_client()
    try:
        resp = ecs.list_tasks(cluster=cluster_name)
        arns = resp.get("taskArns", [])
        if not arns:
            click.echo(json.dumps([], indent=2))
            return
        details = ecs.describe_tasks(cluster=cluster_name, tasks=arns)
        tasks = [
            {
                "taskArn": t.get("taskArn"),
                "lastStatus": t.get("lastStatus"),
                "desiredStatus": t.get("desiredStatus"),
            }
            for t in details.get("tasks", [])
        ]
    except ClientError as e:
        raise click.ClickException(str(e))

    click.echo(json.dumps(tasks, indent=2))


if __name__ == "__main__":
    cli()
