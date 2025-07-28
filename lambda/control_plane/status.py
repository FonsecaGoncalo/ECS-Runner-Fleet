import json
import time

import config
from runners import Runner, register_runner, update_runner


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

    job_state = None
    runner_state = status
    if status in ("idle", "running", "completed"):
        runner_state = "online"
        job_state = status
    elif status == "offline":
        runner_state = "offline"

    runner_rec = Runner(
        id=runner_id,
        state=runner_state,
        job_status=job_state,
        labels=detail.get("runner_labels", ""),
        image=detail.get("image_tag"),
        created_at=ts,
        runner_class=detail.get("class_name"),
        workflow_id=run_key,
        job_id=detail.get("job"),
    )

    if status == "running" and run_key:
        runner_rec.started_at = ts
        register_runner(runner_rec)
        update_runner(
            runner_id,
            repository=detail.get("repository"),
            workflow=detail.get("workflow"),
            job=detail.get("job"),
            started_at=ts,
        )
    elif status in ("offline", "completed"):
        runner_rec.completed_at = ts
        register_runner(runner_rec)

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
    else:
        register_runner(runner_rec)
