import json
import os
from datetime import datetime
from functools import wraps
from typing import Callable, Dict, List, Optional

import boto3
import click
from botocore.exceptions import ClientError


# ---- Helpers for AWS and DynamoDB access ----

def aws_session(profile: Optional[str], region: Optional[str]) -> boto3.Session:
    """Create a boto3 Session using optional profile and region."""
    session_args = {}
    if profile:
        session_args['profile_name'] = profile
    if region:
        session_args['region_name'] = region
    return boto3.Session(**session_args)


def get_dynamo_table(table_name: str, session: boto3.Session):
    """Return a DynamoDB Table resource."""
    return session.resource('dynamodb').Table(table_name)


def get_ssm_param(param_name: str, session: boto3.Session) -> Dict[str, Dict[str, int]]:
    """Fetch JSON parameter from SSM."""
    try:
        client = session.client('ssm')
        resp = client.get_parameter(Name=param_name, WithDecryption=True)
        return json.loads(resp['Parameter']['Value'])
    except ClientError as e:
        raise click.ClickException(f"Failed to fetch SSM parameter {param_name}: {e}")


def get_ecs_client(session: boto3.Session):
    return session.client('ecs')

# ---- Table formatter ----

def format_table(
    items: List[Dict],
    columns: List[tuple],
    stylers: Optional[Dict[str, Callable[[str], str]]] = None
) -> str:
    """Render a text table with optional styling."""
    if not items:
        return '  '.join(click.style(head, bold=True) for head, _ in columns)

    # compute column widths
    widths = [len(head) for head, _ in columns]
    for item in items:
        for i, (_, key) in enumerate(columns):
            widths[i] = max(widths[i], len(str(item.get(key, ''))))

    header = '  '.join(head.ljust(widths[i]) for i, (head, _) in enumerate(columns))
    rows = [click.style(header, bold=True)]
    for item in items:
        parts = []
        for i, (_, key) in enumerate(columns):
            val = str(item.get(key, ''))
            text = val.ljust(widths[i])
            if stylers and key in stylers:
                text = stylers[key](text)
            parts.append(text)
        rows.append('  '.join(parts))
    return '\n'.join(rows)

# ---- Click context ----

class Context:
    def __init__(self, profile: Optional[str], region: Optional[str]):
        self.session = aws_session(profile, region)
        self.region = region
        # Environment-backed defaults
        self.table_name = os.getenv('RUNNER_TABLE') or os.getenv('RUNNER_STATE_TABLE')
        if not self.table_name:
            raise click.ClickException('RUNNER_TABLE environment variable must be set')
        self.ssm_param = os.getenv('CLASS_SIZES_PARAM')

pass_ctx = click.make_pass_decorator(Context)

def common_options(f):
    @click.option('--profile', '-p', help='AWS CLI profile to use')
    @click.option('--region', '-r', help='AWS region')
    @wraps(f)
    def wrapper(*args, **kwargs):
        return f(*args, **kwargs)
    return wrapper

# ---- CLI definition ----
@click.group(context_settings={'help_option_names': ['-h', '--help']})
@common_options
@click.pass_context
def cli(ctx, profile, region):
    """Manage GitHub Actions runners on ECS."""
    ctx.obj = Context(profile, region)

# ---- Class sizes ----
@cli.command('list-class-sizes')
@pass_ctx
def list_class_sizes(ctx):
    """List available runner class sizes from SSM."""
    if not ctx.ssm_param:
        raise click.ClickException('CLASS_SIZES_PARAM not set')
    sizes = get_ssm_param(ctx.ssm_param, ctx.session)
    items = [{'class': name, **vals} for name, vals in sizes.items()]
    columns = [('CLASS', 'class'), ('CPU', 'cpu'), ('MEMORY', 'memory')]
    click.echo(format_table(items, columns))

# ---- Runner commands ----
@cli.group()
def runners():
    """Commands related to individual runners."""
    pass

@runners.command('list')
@pass_ctx
def list_runners(ctx):
    """List all runners and their current status."""
    table = get_dynamo_table(ctx.table_name, ctx.session)
    try:
        resp = table.scan()
        items = resp.get('Items', [])
        while resp.get('LastEvaluatedKey'):
            resp = table.scan(ExclusiveStartKey=resp['LastEvaluatedKey'])
            items.extend(resp.get('Items', []))
    except ClientError as e:
        raise click.ClickException(f'DynamoDB scan failed: {e}')

    columns = [
        ('ID', 'runner_id'),
        ('STATE', 'status'),
        ('JOB', 'job_status'),
        ('STARTED', 'started_at'),
        ('COMPLETED', 'completed_at'),
    ]
    # color based on status
    def style_state(val):
        mapping = {'running':'green', 'waiting_for_job':'yellow', 'failed':'red', 'offline':'red'}
        return click.style(val, fg=mapping.get(val.lower(), None))
    stylers = {'status': style_state}
    # convert epoch to readable
    for item in items:
        for key in ('started_at','completed_at'):
            if key in item:
                item[key] = datetime.fromtimestamp(int(item[key])).isoformat(' ')

    click.echo(format_table(items, columns, stylers))

@runners.command('details')
@pass_ctx
@click.argument('runner_id')
def runner_details(ctx, runner_id):
    """Show the raw DynamoDB record for a runner."""
    table = get_dynamo_table(ctx.table_name, ctx.session)
    try:
        resp = table.get_item(Key={'runner_id': runner_id})
    except ClientError as e:
        raise click.ClickException(f'DynamoDB get_item failed: {e}')
    item = resp.get('Item')
    if not item:
        raise click.ClickException('Runner not found')
    click.echo(json.dumps(item, indent=2))

@runners.command('terminate')
@pass_ctx
@click.option('--cluster', required=True, help='ECS cluster name')
@click.argument('task_arn')
def terminate_runner(ctx, task_arn, cluster):
    """Stop a running ECS task by ARN."""
    ecs = get_ecs_client(ctx.session)
    try:
        ecs.stop_task(cluster=cluster, task=task_arn, reason='Stopped via CLI')
    except ClientError as e:
        raise click.ClickException(f'ECS stop_task failed: {e}')
    click.secho('Task termination initiated', fg='green')

# ---- Cluster commands ----
@cli.group()
def cluster():
    """Cluster-level ECS commands."""
    pass

@cluster.command('status')
@pass_ctx
@click.argument('cluster_name')
def cluster_status(ctx, cluster_name):
    """List tasks in an ECS cluster."""
    ecs = get_ecs_client(ctx.session)
    try:
        resp = ecs.list_tasks(cluster=cluster_name)
        arns = resp.get('taskArns', [])
        if not arns:
            click.echo('No tasks found')
            return
        details = ecs.describe_tasks(cluster=cluster_name, tasks=arns)
        tasks = [{'taskArn': t['taskArn'], 'status': t['lastStatus']} for t in details.get('tasks', [])]
    except ClientError as e:
        raise click.ClickException(f'ECS describe_tasks failed: {e}')
    click.echo(format_table(tasks, [('TASK', 'taskArn'), ('STATUS', 'status')]))

# ---- Entry point ----
if __name__ == '__main__':
    cli()
