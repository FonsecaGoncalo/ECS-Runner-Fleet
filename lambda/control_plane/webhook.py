import base64
import hashlib
import hmac
import json

import config
from image import ensure_image_exists
import runner


def handle_webhook_event(event):
    """Handle incoming GitHub webhook events."""
    body = event.get("body")
    if body is None:
        print("No body in event")
        return {"statusCode": 400, "body": "no event body"}

    if event.get("isBase64Encoded"):
        body_bytes = base64.b64decode(body)
        body_str = body_bytes.decode()
    else:
        body_bytes = body.encode()
        body_str = body

    signature = event.get("headers", {}).get("x-hub-signature-256")
    if not signature:
        print("Missing signature header")
        return {"statusCode": 401, "body": "missing signature"}

    expected = "sha256=" + hmac.new(
        config.WEBHOOK_SECRET.encode(), body_bytes, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(signature, expected):
        print("Invalid webhook signature")
        return {"statusCode": 401, "body": "invalid signature"}
    try:
        payload = json.loads(body_str)
    except json.JSONDecodeError:
        print("Invalid JSON payload")
        return {"statusCode": 400, "body": "invalid json"}

    action = payload.get("action")
    if action != "queued" or "workflow_job" not in payload:
        print(f"Ignoring action: {action}")
        return {"statusCode": 200, "body": "ignored"}

    job = payload.get("workflow_job", {})
    job_labels = job.get("labels", [])
    runner_labels = ",".join(job_labels) if job_labels else "default-runner"

    base_image = None
    class_name = None
    for lbl in job_labels:
        if lbl.startswith("image:"):
            base_image = lbl.split(":", 1)[1]
        elif lbl.startswith("class:"):
            class_name = lbl.split(":", 1)[1]

    if base_image:
        try:
            image_uri = ensure_image_exists(base_image, runner_labels, class_name)
            if image_uri is None:
                print("Image build triggered, exiting")
                return {"statusCode": 202, "body": "image build"}
            label = f"image:{base_image}"
            print(f"Using dynamic image {image_uri}")
        except Exception as exc:
            print(f"Failed to prepare image {base_image}: {exc}")
            return {"statusCode": 500, "body": "image build failed"}
    else:
        image_uri = f"{config.ECR_REPOSITORY}:{config.RUNNER_IMAGE_TAG}"
        label = None
    runner.run_runner_task(
        image_uri,
        runner_labels,
        class_name,
        label,
        repo=config.GITHUB_REPO,
        pat=config.GITHUB_PAT,
    )
    return {"statusCode": 200, "body": "task started"}
