from __future__ import annotations

import json
import time
from typing import Any, Dict

from aws_lambda_powertools import Logger, Tracer

from ..config import Settings, client, resource
from ..models import Runner


class StatusService:
    def __init__(
        self, settings: Settings, logger: Logger, tracer: Tracer
    ) -> None:  
        self.settings = settings
        self.logger = logger
        self.tracer = tracer
        self.table = resource("dynamodb").Table(settings.runner_table)
        self.ecs = client("ecs")

    def handle_event(self, detail: Dict[str, Any]) -> None:
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
            self.register_runner(runner_rec)
            self.update_runner(
                runner_id,
                repository=detail.get("repository"),
                workflow=detail.get("workflow"),
                job=detail.get("job"),
                started_at=ts,
            )
        elif status in ("offline", "completed"):
            runner_rec.completed_at = ts
            self.register_runner(runner_rec)
            if status == "completed" and runner_id:
                task_id = runner_id.split("-")[-1]
                try:
                    self.ecs.stop_task(
                        cluster=self.settings.cluster,
                        task=task_id,
                        reason="runner job completed",
                    )
                except Exception as exc:  # pragma: no cover - logging only
                    self.logger.exception(
                        "Failed to stop task",
                        extra={"task_id": task_id, "error": str(exc)},
                    )
        else:
            self.register_runner(runner_rec)

    def register_runner(self, runner: Runner) -> None:
        self.table.put_item(Item=runner.to_item())

    def update_runner(self, runner_id: str, **attrs: Any) -> None:
        names = {}
        values = {}
        updates = []
        for idx, (key, val) in enumerate(attrs.items()):
            name = f"#n{idx}"
            value = f":v{idx}"
            names[name] = key
            values[value] = val
            updates.append(f"{name} = {value}")
        expr = "SET " + ", ".join(updates)
        self.table.update_item(
            Key={"runner_id": runner_id, "item_id": "state"},
            UpdateExpression=expr,
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
        )
