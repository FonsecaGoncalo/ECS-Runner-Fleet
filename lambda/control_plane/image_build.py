import config
import runner
from runners import get_item, update_item, delete_item


def handle_image_build_event(detail):
    """Handle CodeBuild image build completion events."""
    build_id = detail.get("build_id")
    image_uri = detail.get("image_uri")
    status = detail.get("status")

    if not build_id:
        return {"statusCode": 400, "body": "missing build id"}

    item = get_item({"runner_id": build_id, "item_id": "state"})
    if not item:
        print(f"No entry for build {build_id}")
        return {"statusCode": 200, "body": "no entry"}

    if status != "SUCCEEDED":
        update_item(
            {"runner_id": build_id, "item_id": "state"},
            UpdateExpression="SET #s = :failed",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":failed": "image failed"},
        )
        return {"statusCode": 200, "body": "build failed"}

    runner_labels = item.get("runner_labels", "default-runner")
    class_name = item.get("class_name")
    image_label = f"image:{item.get('image_tag')}"

    runner.run_runner_task(
        image_uri,
        runner_labels,
        class_name,
        image_label,
        repo=config.GITHUB_REPO,
        pat=config.GITHUB_PAT,
    )

    delete_item({"runner_id": build_id, "item_id": "state"})
    return {"statusCode": 200, "body": "runner started"}
