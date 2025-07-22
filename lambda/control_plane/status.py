import json
import time

from . import config


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

    table = config.dynamodb.Table(config.RUNNER_TABLE)
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
        table.put_item(
            Item={
                "runner_id": runner_id,
                "item_id": f"run#{run_key}",
                "run_id": run_key,
                "repository": detail.get("repository"),
                "workflow": detail.get("workflow"),
                "job": detail.get("job"),
                "started_at": ts,
            }
        )
    elif status in ("idle", "offline"):
        state_item["completed_at"] = ts
        if run_key:
            try:
                table.update_item(
                    Key={"runner_id": runner_id, "item_id": f"run#{run_key}"},
                    UpdateExpression="SET completed_at = :ts",
                    ExpressionAttributeValues={":ts": ts},
                )
            except Exception as exc:
                print(f"Failed to update run record: {exc}")

    table.put_item(Item=state_item)
