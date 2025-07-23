import json
import time

import config
from runners import put_item, update_item


def handle_status_event(detail) -> None:
    """Persist runner status updates to DynamoDB."""
    if isinstance(detail, str):
        try:
            detail = json.loads(detail)
        except json.JSONDecodeError:
            detail = {}
    status = detail.get("status")
    runner_id = detail.get("runner_id")
    ts = detail.get("timestamp", int(time.time()))
    run_key = detail.get("workflow_job_id")

    state_item = {
        "runner_id": runner_id,
        "item_id": "state",
        "status": status,
        "timestamp": ts,
    }
    if run_key:
        state_item["workflow_job_id"] = run_key

    if status == "running" and run_key:
        state_item["started_at"] = ts
        put_item(
            item={
                "runner_id": runner_id,
                "item_id": f"run#{run_key}",
                "run_id": run_key,
                "repository": detail.get("repository"),
                "workflow": detail.get("workflow"),
                "job": detail.get("job"),
                "started_at": ts,
            }
        )
    elif status in ("idle", "offline", "completed"):
        state_item["completed_at"] = ts
        if run_key:
            try:
                update_item(
                    {"runner_id": runner_id, "item_id": f"run#{run_key}"},
                    UpdateExpression="SET completed_at = :ts",
                    ExpressionAttributeValues={":ts": ts},
                )
            except Exception as exc:
                print(f"Failed to update run record: {exc}")

        if status == "completed" and runner_id:
            task_id = runner_id.split("-")[-1]
            try:
                config.ecs.stop_task(
                    cluster=config.CLUSTER,
                    task=task_id,
                    reason="runner job completed",
                )
            except Exception as exc:
                print(f"Failed to stop task {task_id}: {exc}")

    put_item(state_item)
