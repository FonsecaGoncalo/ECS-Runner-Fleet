import json

from status import handle_status_event
from image_build import handle_image_build_event
from webhook import handle_webhook_event


def lambda_handler(event, context):
    """Entry point for the runner control plane Lambda."""
    print("Received event:", json.dumps(event))

    detail_type = event.get("detail-type")
    if detail_type == "runner-status":
        handle_status_event(event.get("detail"))
        return {"statusCode": 200, "body": "status updated"}

    if detail_type == "image-build":
        return handle_image_build_event(event.get("detail", {}))

    return handle_webhook_event(event)
