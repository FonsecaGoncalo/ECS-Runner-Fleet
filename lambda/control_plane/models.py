from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class EventType(str, Enum):
    RUNNER_STATUS = "runner-status"
    IMAGE_BUILD = "image-build"
    WEBHOOK = "workflow_job"


@dataclass
class Runner:
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
    job_status: Optional[str] = None

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
        if self.job_status:
            item["job_status"] = self.job_status
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
            job_status=item.get("job_status"),
        )
