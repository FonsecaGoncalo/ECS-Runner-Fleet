from __future__ import annotations

import time
from typing import Dict, Any

from aws_lambda_powertools import Logger, Tracer

from config import Settings, resource
from models import Runner, RunnerState
from runner_controller import RunnerController


logger = Logger(service="runner-janitor")
tracer = Tracer(service="runner-janitor")
settings = Settings()


@logger.inject_lambda_context
@tracer.capture_lambda_handler
def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    controller = RunnerController(settings)
    table = resource("dynamodb").Table(settings.runner_table)

    now = int(time.time())
    ttl = settings.runner_ttl_seconds

    scanned = 0
    cleaned = 0

    exclusive_start_key = None
    while True:
        scan_kwargs: Dict[str, Any] = {}
        if exclusive_start_key:
            scan_kwargs["ExclusiveStartKey"] = exclusive_start_key
        resp = table.scan(**scan_kwargs)
        items = resp.get("Items", [])
        scanned += len(items)

        for item in items:
            runner = Runner.from_item(item)
            age = now - (runner.created_at or now)
            if age < ttl:
                continue

            try:
                # Determine if this runner should be marked as FAILED vs OFFLINE
                should_fail = runner.state in {
                    RunnerState.IMAGE_CREATING,
                    RunnerState.STARTING,
                    RunnerState.WAITING_FOR_JOB,
                    RunnerState.RUNNING,
                }

                if runner.task_id:
                    # Stop any lingering task first
                    controller.terminate_runner(runner.id)
                    if should_fail and runner.state == RunnerState.RUNNING:
                        # Explicitly fail long-running tasks beyond TTL
                        controller.update_runner_state(runner.id, RunnerState.FAILED)
                else:
                    # No task running: mark according to state
                    controller.update_runner_state(
                        runner.id, RunnerState.FAILED if should_fail else RunnerState.OFFLINE
                    )
                cleaned += 1
            except Exception:
                logger.exception(
                    "Janitor failed to reconcile runner",
                    extra={
                        "runner_id": runner.id,
                        "state": getattr(runner.state, "value", runner.state),
                        "task_id": runner.task_id,
                        "age": age,
                    },
                )

        exclusive_start_key = resp.get("LastEvaluatedKey")
        if not exclusive_start_key:
            break

    return {
        "statusCode": 200,
        "body": f"scanned={scanned} cleaned={cleaned} ttl={ttl}",
    }
