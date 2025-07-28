from __future__ import annotations

from aws_lambda_powertools import Logger, Tracer

from .config import Settings
from .models import EventType
from .services.image_build_service import ImageBuildService
from .services.status_service import StatusService
from .services.webhook_service import WebhookService

logger = Logger(service="control-plane")
tracer = Tracer(service="control-plane")
settings = Settings()

status_service = StatusService(settings, logger, tracer)
image_build_service = ImageBuildService(settings, logger, tracer)
webhook_service = WebhookService(settings, logger, tracer)


@logger.inject_lambda_context
@tracer.capture_lambda_handler
def lambda_handler(event: dict, context) -> dict:
    detail_type = event.get("detail-type")
    try:
        if detail_type == EventType.RUNNER_STATUS.value:
            status_service.handle_event(event.get("detail", {}))
            return {"statusCode": 200, "body": "status updated"}
        if detail_type == EventType.IMAGE_BUILD.value:
            return image_build_service.handle_event(event.get("detail", {}))
        return webhook_service.handle_event(event)
    except ValueError as exc:
        logger.exception("Invalid request")
        return {"statusCode": 400, "body": str(exc)}
    except Exception:
        logger.exception("Unhandled error")
        return {"statusCode": 500, "body": "internal error"}
