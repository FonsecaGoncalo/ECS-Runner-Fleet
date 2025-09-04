from __future__ import annotations

from typing import Any, Dict

from aws_lambda_powertools import Logger, Tracer

from config import Settings, resource
from runner_controller import RunnerController


class ImageBuildService:
    def __init__(
            self, settings: Settings, logger: Logger, tracer: Tracer
    ) -> None:
        self.settings = settings
        self.logger = logger
        self.tracer = tracer
        self.runner_controller = RunnerController(settings)

    def handle_event(self, detail: Dict[str, Any]) -> Dict[str, Any]:
        build_id = detail.get("build_id")
        image_uri = detail.get("image_uri")
        status = detail.get("status")
        runner_id = detail.get("runner_id")

        self.logger.info(f"Detail: {detail}")
        self.logger.info(f"runner_id: {runner_id}")
        self.logger.info(f"Build ID: {build_id}, Image URI: {image_uri}")

        if not runner_id:
            return {"statusCode": 400, "body": "missing runner id"}
        if not image_uri:
            # Build did not produce image URI; treat as failure unless status says otherwise
            self.runner_controller.mark_runner_as_failed(runner_id)
            return {"statusCode": 400, "body": "missing image uri"}

        if status != "SUCCEEDED":
            self.runner_controller.mark_runner_as_failed(runner_id)
            return {"statusCode": 200, "body": "build failed"}

        self.runner_controller.start_runner(runner_id)
        return {"statusCode": 200, "body": "runner started"}
