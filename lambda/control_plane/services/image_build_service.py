from __future__ import annotations

from typing import Any, Dict

from aws_lambda_powertools import Logger, Tracer

from ..config import Settings, resource
from ..utilities.runner import run_runner_task


class ImageBuildService:
    def __init__(
            self, settings: Settings, logger: Logger, tracer: Tracer
    ) -> None:
        self.settings = settings
        self.logger = logger
        self.tracer = tracer
        self.table = resource("dynamodb").Table(settings.runner_table)

    def handle_event(self, detail: Dict[str, Any]) -> Dict[str, Any]:
        build_id = detail.get("build_id")
        image_uri = detail.get("image_uri")
        status = detail.get("status")
        if not build_id:
            return {"statusCode": 400, "body": "missing build id"}
        item = self.table.get_item(
            Key={"runner_id": build_id, "item_id": "state"}
        ).get(
            "Item"
        )
        if not item:
            self.logger.info(
                "No entry for build", extra={"build_id": build_id}
            )
            return {"statusCode": 200, "body": "no entry"}
        if status != "SUCCEEDED":
            self.table.update_item(
                Key={"runner_id": build_id, "item_id": "state"},
                UpdateExpression="SET #s = :failed",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={":failed": "image failed"},
            )
            return {"statusCode": 200, "body": "build failed"}
        runner_labels = item.get("runner_labels", "default")
        class_name = item.get("class_name")
        image_label = f"image:{item.get('image_tag')}"
        run_runner_task(
            settings=self.settings,
            image_uri=image_uri,
            runner_labels=runner_labels,
            class_name=class_name,
            label=image_label,
        )
        self.table.delete_item(Key={"runner_id": build_id, "item_id": "state"})
        return {"statusCode": 200, "body": "runner started"}
