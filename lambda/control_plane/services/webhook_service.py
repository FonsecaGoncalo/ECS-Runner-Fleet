from __future__ import annotations

import base64
import json
from typing import Any, Dict

from aws_lambda_powertools import Logger, Tracer

from config import Settings
from models import RunnerState
from runner_controller import RunnerController
from utilities.signature import verify_github_signature


class WebhookService:
    def __init__(
            self, settings: Settings, logger: Logger, tracer: Tracer
    ) -> None:
        self.settings = settings
        self.logger = logger
        self.tracer = tracer
        self.runner_controller = RunnerController(settings)

    def handle_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        body = event.get("body")
        if body is None:
            return {"statusCode": 400, "body": "no event body"}
        if event.get("isBase64Encoded"):
            body_bytes = base64.b64decode(body)
            body_str = body_bytes.decode()
        else:
            body_bytes = body.encode()
            body_str = body
        headers = event.get("headers", {}) or {}
        signature = (
            headers.get("x-hub-signature-256") or headers.get("X-Hub-Signature-256")
        )
        if not signature:
            return {"statusCode": 401, "body": "missing signature"}
        if not verify_github_signature(
                body_bytes, self.settings.github_webhook_secret, signature.strip()
        ):
            return {"statusCode": 401, "body": "invalid signature"}
        try:
            payload = json.loads(body_str)
        except json.JSONDecodeError:
            return {"statusCode": 400, "body": "invalid json"}
        action = payload.get("action")
        if action != "queued" or "workflow_job" not in payload:
            return {"statusCode": 200, "body": "ignored"}
        job = payload.get("workflow_job", {})
        job_labels = job.get("labels", [])
        if not job_labels:
            return {"statusCode": 400, "body": "missing labels"}
        runner_labels = ",".join(job_labels)
        base_image = None
        class_name = None

        for lbl in job_labels:
            if lbl.startswith("image:"):
                base_image = lbl.split(":", 1)[1]
            elif lbl.startswith("class:"):
                class_name = lbl.split(":", 1)[1]

        if base_image is None:
            return {"statusCode": 400, "body": "no base image"}

        runner = self.runner_controller.new_runner(runner_labels, base_image, class_name)

        if runner.state == RunnerState.IMAGE_CREATING:
            return {"statusCode": 202, "body": "image build"}
        elif runner.state == RunnerState.WAITING_FOR_JOB:
            return {"statusCode": 200, "body": "task started"}
        else:
            return {"statusCode": 500, "body": "unknown state"}
