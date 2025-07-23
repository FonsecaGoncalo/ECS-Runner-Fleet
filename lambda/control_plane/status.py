import json
import time

import config
from runners import Runner, register_runner, update_item, update_runner


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

    runner_rec = Runner(
        id=runner_id,
        state=status,
        labels=detail.get("runner_labels", ""),
        image=detail.get("image_tag"),
        created_at=ts,
        runner_class=detail.get("class_name"),
        workflow_id=run_key,
        job_id=detail.get("job"),
    )

    if status == "running" and run_key:
        runner_rec.started_at = ts
        update_runner(runner_id,
                      repository=detail.get("repository"),
                      workflow=detail.get("workflow"),
                      job=detail.get("job"),
                      started_at=ts,
                      )
    elif status in ("idle", "offline", "completed"):
        runner_rec.completed_at = ts

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

    register_runner(runner_rec)
