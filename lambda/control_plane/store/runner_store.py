from datetime import time
from typing import Optional

import ulid

from ..config import Settings, resource
from ..models import Runner, RunnerState


class RunnerStore:

    def __init__(self,
                 settings: Settings):
        self.settings = settings
        self.table = resource("dynamodb").Table(settings.runner_table)

    def new_runner(self, runner_labels, tag, class_name) -> Runner:
        runner = Runner(
            id=str(ulid.ulid()),
            state=RunnerState.STARTING,
            labels=runner_labels,
            image=tag,
            created_at=int(time.time()),
            runner_class=class_name,
        )
        self.table.put_item(Item=runner.to_item())
        return runner

    def get_runner(self, runner_id: str) -> Optional[Runner]:
        resp = self.table.get_item(Key={"runner_id": runner_id})
        item = resp.get("Item")
        if not item:
            return None
        return Runner.from_item(item)

    def save(self, runner: Runner) -> Runner:
        self.table.put_item(Item=runner.to_item())
        return runner