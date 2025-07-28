from __future__ import annotations

import base64
import json
import time
from typing import Any, Dict, Optional

import ulid
from aws_lambda_powertools import Logger, Tracer

from ..config import Settings, client, resource
from ..models import Runner
from ..utilities.images import sanitize_image_label
from ..utilities.runner import run_runner_task
from ..utilities.signature import verify_github_signature


class WebhookService:
    def __init__(
        self, settings: Settings, logger: Logger, tracer: Tracer
    ) -> None:  
        self.settings = settings
        self.logger = logger
        self.tracer = tracer
        self.table = resource("dynamodb").Table(settings.runner_table)
        self.ecr = client("ecr")
        self.codebuild = (
            client("codebuild") if settings.image_build_project else None
        )  

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
        signature = event.get("headers", {}).get("x-hub-signature-256")
        if not signature:
            return {"statusCode": 401, "body": "missing signature"}
        if not verify_github_signature(
            body_bytes, self.settings.webhook_secret, signature
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
        image_uri = self._get_image(base_image)
        if image_uri is None:
            tag = sanitize_image_label(base_image)
            self._start_build(base_image)
            runner_rec = Runner(
                id=str(ulid.ulid()),
                state="image creating",
                labels=runner_labels,
                image=tag,
                created_at=int(time.time()),
                runner_class=class_name,
            )
            self.table.put_item(Item=runner_rec.to_item())
            return {"statusCode": 202, "body": "image build"}
        label = f"image:{base_image}"
        run_runner_task(
            settings=self.settings,
            image_uri=image_uri,
            runner_labels=runner_labels,
            class_name=class_name,
            label=label,
        )
        return {"statusCode": 200, "body": "task started"}

    def _get_image(self, base_image: str) -> Optional[str]:
        repo_name = self.settings.ecr_repository_url.split("/")[-1]
        tag = sanitize_image_label(base_image)
        try:
            self.ecr.describe_images(
                repositoryName=repo_name, imageIds=[{"imageTag": tag}]
            )
            return f"{self.settings.ecr_repository_url}:{tag}"
        except self.ecr.exceptions.ImageNotFoundException:
            return None

    def _start_build(self, base_image: str) -> None:
        if not self.codebuild:
            raise Exception("Dynamic image build not configured")
        repo_name = self.settings.ecr_repository_url.split("/")[-1]
        tag = sanitize_image_label(base_image)
        self.codebuild.start_build(
            projectName=self.settings.image_build_project,
            environmentVariablesOverride=[
                {
                    "name": "BASE_IMAGE",
                    "value": base_image,
                    "type": "PLAINTEXT",
                },
                {"name": "TAG", "value": tag, "type": "PLAINTEXT"},
                {
                    "name": "REPOSITORY",
                    "value": repo_name,
                    "type": "PLAINTEXT",
                },
                {
                    "name": "EVENT_BUS_NAME",
                    "value": self.settings.event_bus_name,
                    "type": "PLAINTEXT",
                },
            ],
        )
