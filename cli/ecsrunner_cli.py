"""Command line tool to manage ECS-based GitHub Actions runners."""
import json
import os
import shutil
import subprocess
from typing import Callable, Dict

import boto3
import click
from botocore.exceptions import ClientError


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


def _get_class_sizes():
    """Return dict of runner class sizes from SSM."""
    param_name = os.environ.get("CLASS_SIZES_PARAM")
    if not param_name:
        raise click.ClickException("CLASS_SIZES_PARAM environment variable is not set")
    ssm = boto3.client("ssm")
    try:
        resp = ssm.get_parameter(Name=param_name)
        return json.loads(resp["Parameter"]["Value"])
    except ClientError as e:
        raise click.ClickException(str(e))


def _format_table(
        items,
        columns,
        stylers: Dict[str, Callable[[str], str]] | None = None,
):
    """Return a simple table string for a list of dicts.

    Parameters
    ----------
    items: list of dict
        Items to render.
    columns: list of tuple
        Sequence of ``(header, key)`` column definitions.
    """

    if not items:
        headers = [c[0] for c in columns]
        return "  ".join(click.style(h, bold=True) for h in headers)

    widths = [len(col[0]) for col in columns]
    for item in items:
        for idx, (_, key) in enumerate(columns):
            widths[idx] = max(widths[idx], len(str(item.get(key, ""))))

    header = "  ".join(col[0].ljust(widths[i]) for i, col in enumerate(columns))
    rows = [click.style(header, bold=True)]
    for item in items:
        parts = []
        for i, (header_name, key) in enumerate(columns):
            raw = str(item.get(key, ""))
            padded = raw.ljust(widths[i])
            if stylers and key in stylers:
                padded = stylers[key](padded)
            parts.append(padded)
        rows.append("  ".join(parts))
    return "\n".join(rows)


# Main CLI group ---------------------------------------------------------

@click.group()
def cli():
    """Manage GitHub Actions runners on ECS."""
    pass


@cli.command("list-class-sizes")
def list_class_sizes():
    """List available runner class sizes."""
    sizes = _get_class_sizes()
    items = [{"class": name, **vals} for name, vals in sizes.items()]
    columns = [("CLASS", "class"), ("CPU", "cpu"), ("MEMORY", "memory")]
    click.echo(_format_table(items, columns))


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

    columns = [
        ("RUNNER_ID", "runner_id"),
        ("STATUS", "status"),
        ("JOB_ID", "workflow_job_id"),
        ("STARTED", "started_at"),
        ("COMPLETED", "completed_at"),
    ]

    def color_status(text: str) -> str:
        raw = text.strip()
        color = {
            "running": "green",
            "idle": "yellow",
            "stopped": "red",
        }.get(raw.lower())
        return click.style(text, fg=color) if color else text

    stylers = {"status": color_status}

    click.echo(_format_table(items, columns, stylers))


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

    for key in sorted(item):
        click.echo(f"{key}: {item[key]}")


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
    if shutil.which("session-manager-plugin") is None:
        raise click.ClickException(
            "Session Manager plugin not found. "
            "See https://docs.aws.amazon.com/console/systems-manager/session-manager-plugin-not-found"
        )
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
            click.echo("No tasks found")
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

    columns = [
        ("TASK_ARN", "taskArn"),
        ("DESIRED", "desiredStatus"),
        ("LAST", "lastStatus"),
    ]

    def color_task_status(text: str) -> str:
        raw = text.strip()
        color = {
            "running": "green",
            "pending": "yellow",
            "stopped": "red",
        }.get(raw.lower())
        return click.style(text, fg=color) if color else text

    stylers = {"desiredStatus": color_task_status, "lastStatus": color_task_status}

    click.echo(_format_table(tasks, columns, stylers))


# Runs commands ----------------------------------------------------------

@cli.group()
def runs():
    """Commands related to runner job history."""
    pass


@runs.command("list")
@click.option("--runner-id", help="Filter by runner id")
def list_runs(runner_id):
    """List recorded workflow runs."""
    table = _get_table()
    items = []
    try:
        from boto3.dynamodb.conditions import Key, Attr

        if runner_id:
            resp = table.query(
                KeyConditionExpression=Key("runner_id").eq(runner_id)
                & Key("item_id").begins_with("run#")
            )
            items.extend(resp.get("Items", []))
            while resp.get("LastEvaluatedKey"):
                resp = table.query(
                    KeyConditionExpression=Key("runner_id").eq(runner_id)
                    & Key("item_id").begins_with("run#"),
                    ExclusiveStartKey=resp["LastEvaluatedKey"],
                )
                items.extend(resp.get("Items", []))
        else:
            resp = table.scan(FilterExpression=Attr("item_id").begins_with("run#"))
            items.extend(resp.get("Items", []))
            while resp.get("LastEvaluatedKey"):
                resp = table.scan(
                    FilterExpression=Attr("item_id").begins_with("run#"),
                    ExclusiveStartKey=resp["LastEvaluatedKey"],
                )
                items.extend(resp.get("Items", []))
    except ClientError as e:
        raise click.ClickException(str(e))

    columns = [
        ("RUNNER_ID", "runner_id"),
        ("RUN_ID", "run_id"),
        ("REPOSITORY", "repository"),
        ("WORKFLOW", "workflow"),
        ("JOB", "job"),
        ("STARTED", "started_at"),
        ("COMPLETED", "completed_at"),
    ]

    click.echo(_format_table(items, columns))


if __name__ == "__main__":
    cli()
