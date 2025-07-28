from __future__ import annotations

import json
import time
from typing import Any, Dict

from aws_lambda_powertools import Logger, Tracer

from ..config import Settings, client, resource
from ..models import Runner, RunnerState
from ..runner_controller import RunnerController


class StatusService:
    def __init__(
            self, settings: Settings, logger: Logger, tracer: Tracer
    ) -> None:
        self.settings = settings
        self.logger = logger
        self.tracer = tracer
        self.runner_controller = RunnerController(settings)

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

        if status in "RUNNING":
            self.runner_controller.update_runner_state(runner_id, RunnerState.RUNNING)
        elif status == "OFFLINE":
            self.runner_controller.terminate_runner(runner_id)
