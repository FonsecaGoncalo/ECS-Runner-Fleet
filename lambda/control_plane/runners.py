from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
import time

import config

_table = None


def get_table():
    """Return cached DynamoDB table for runner state."""
    global _table
    if _table is None:
        if not config.RUNNER_TABLE:
            raise RuntimeError("RUNNER_TABLE environment variable not set")
        _table = config.dynamodb.Table(config.RUNNER_TABLE)
    return _table


def get_item(key: dict) -> dict | None:
    return get_table().get_item(Key=key).get("Item")


@dataclass
class Runner:
    """Representation of a single runner instance."""

    id: str
    state: str
    labels: str
    image: Optional[str] = None
    created_at: int = field(default_factory=lambda: int(time.time()))
    started_at: Optional[int] = None
    completed_at: Optional[int] = None
    runner_class: Optional[str] = None
    workflow_id: Optional[str] = None
    job_id: Optional[str] = None

    def to_item(self) -> dict:
        item = {
            "runner_id": self.id,
            "item_id": "state",
            "status": self.state,
            "timestamp": self.created_at,
        }
        if self.labels:
            item["runner_labels"] = self.labels
        if self.image:
            item["image_tag"] = self.image
        if self.started_at is not None:
            item["started_at"] = self.started_at
        if self.completed_at is not None:
            item["completed_at"] = self.completed_at
        if self.runner_class:
            item["class_name"] = self.runner_class
        if self.workflow_id:
            item["workflow_job_id"] = self.workflow_id
        if self.job_id:
            item["job_id"] = self.job_id
        return item

    @classmethod
    def from_item(cls, item: dict) -> "Runner":
        return cls(
            id=item.get("runner_id"),
            state=item.get("status"),
            labels=item.get("runner_labels", ""),
            image=item.get("image_tag"),
            created_at=item.get("timestamp", int(time.time())),
            started_at=item.get("started_at"),
            completed_at=item.get("completed_at"),
            runner_class=item.get("class_name"),
            workflow_id=item.get("workflow_job_id"),
            job_id=item.get("job_id"),
        )


def get_runner(runner_id: str) -> Optional[Runner]:
    item = get_table().get_item(
        Key={"runner_id": runner_id, "item_id": "state"}
    ).get("Item")
    return Runner.from_item(item) if item else None


def register_runner(runner: Runner) -> None:
    get_table().put_item(Item=runner.to_item())


def update_runner(runner_id: str, **attrs) -> None:
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
    get_table().update_item(
        Key={"runner_id": runner_id, "item_id": "state"},
        UpdateExpression=expr,
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
    )

def update_item(key: dict, **kwargs) -> None:
    get_table().update_item(Key=key, **kwargs)


def delete_runner(runner_id: str) -> None:
    get_table().delete_item(Key={"runner_id": runner_id, "item_id": "state"})


def delete_item(key: dict) -> None:
    get_table().delete_item(Key=key)
