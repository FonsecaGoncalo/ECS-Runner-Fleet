import logging
from typing import Optional, Dict, Any, Iterable

from botocore.exceptions import ClientError

from models import Runner, RunnerState
from config import Settings, client, get_class_sizes
from store.runner_store import RunnerStore
from utilities import images as img_utils, runner as runner_utils

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class RunnerController:
    """
    Responsible for provisioning, launching, and tearing down
    GitHub Actions runners on AWS (ECR, ECS, CodeBuild).
    """

    def __init__(
            self,
            settings: Settings,
            runner_store: RunnerStore = None,
            ecr_client=None,
            ecs_client=None,
            codebuild_client=None,
    ):
        self.settings = settings
        self.runner_store = runner_store or RunnerStore(settings)
        self.ecr = ecr_client or client("ecr")
        self.ecs = ecs_client or client("ecs")
        self.codebuild = codebuild_client or (
            client("codebuild") if settings.image_build_project else None
        )

        # Pre-calc repository name
        self._repo_name = settings.ecr_repository_url.rsplit("/", 1)[-1]

    def new_runner(
            self, labels: Iterable[str], base_image: str, class_name: str
    ) -> Runner:
        """
        Create a new Runner record and either:
          1) Trigger an image build (if not present) -> IMAGE_CREATING
          2) Launch an ECS task immediately       -> RUNNING
        """
        tag = img_utils.sanitize_image_label(base_image)
        runner = self.runner_store.new_runner(labels, tag, class_name)

        image_uri = self._resolve_image_uri(tag)
        if image_uri is None:
            logger.info("Image %s not found in ECR, queuing build", tag)
            runner.state = RunnerState.IMAGE_CREATING
            self.runner_store.save(runner)
            self._build_image_async(base_image, tag, runner.id)
            return runner

        logger.info("Found image %s, launching runner task", image_uri)
        task_id = self._launch_runner_task(image_uri, labels, tag, class_name)
        runner.state = RunnerState.WAITING_FOR_JOB
        runner.task_id = task_id
        self.runner_store.save(runner)
        return runner

    def mark_runner_as_failed(
            self, runner_id: str
    ):
        runner = self.runner_store.get_runner(runner_id)
        runner.state = RunnerState.FAILED
        self.runner_store.save(runner)

    def start_runner(self, runner_id: str) -> Runner:
        runner = self.runner_store.get_runner(runner_id)

        if runner is None:
            raise RuntimeError(f"Runner {runner_id} not found")

        if runner.state != RunnerState.IMAGE_CREATING:
            raise RuntimeError(f"Runner {runner_id} state is {runner.state}")

        tag = img_utils.sanitize_image_label(runner.image)
        image_uri = self._resolve_image_uri(tag)

        task_id = self._launch_runner_task(image_uri, runner.labels, runner.runner_class)
        runner.state = RunnerState.WAITING_FOR_JOB
        runner.task_id = task_id
        self.runner_store.save(runner)
        return runner

    def _resolve_image_uri(self, tag: str) -> Optional[str]:
        """Return the full ECR URI if the tag exists, else None."""
        try:
            self.ecr.describe_images(
                repositoryName=self._repo_name,
                imageIds=[{"imageTag": tag}],
            )
            return f"{self.settings.ecr_repository_url}:{tag}"
        except self.ecr.exceptions.ImageNotFoundException:
            return None
        except ClientError as e:
            logger.error("ECR lookup failed: %s", e)
            raise

    def update_runner_state(self, runner_id: str, state: RunnerState) -> Runner:
        runner = self.runner_store.get_runner(runner_id)
        runner.state = state
        self.runner_store.save(runner)
        return runner

    def terminate_runner(self, runner_id: str) -> Runner:
        runner = self.runner_store.get_runner(runner_id)
        task_id = runner.task_id

        try:
            self.ecs.stop_task(
                cluster=self.settings.cluster,
                task=task_id,
                reason="Runner job completed",
            )

            runner.state = RunnerState.OFFLINE
        except Exception as exc:  # pragma: no cover - logging only
            logger.exception(
                "Failed to stop task",
                extra={"task_id": task_id, "error": str(exc)},
            )

    def _build_image_async(self, base_image: str, tag: str, runner_id: str) -> None:
        """Kick off a CodeBuild project to build & push a new runner image."""
        if not self.codebuild:
            raise RuntimeError("Image build project is not configured")
        env_vars = [
            {"name": "BASE_IMAGE", "value": base_image, "type": "PLAINTEXT"},
            {"name": "TAG", "value": tag, "type": "PLAINTEXT"},
            {"name": "REPOSITORY", "value": self._repo_name, "type": "PLAINTEXT"},
            {"name": "EVENT_BUS_NAME", "value": self.settings.event_bus_name, "type": "PLAINTEXT"},
            {"name": "RUNNER_ID", "value": runner_id, "type": "PLAINTEXT"},
        ]
        logger.debug("Starting CodeBuild project %s with vars %s",
                     self.settings.image_build_project, env_vars)
        self.codebuild.start_build(
            projectName=self.settings.image_build_project,
            environmentVariablesOverride=env_vars,
        )

    def _launch_runner_task(
            self,
            image_uri: str,
            labels: Iterable[str],
            tag: str,
            class_name: Optional[str] = None,
    ) -> str:
        """
        Run a Fargate task for the runner.
        Applies class-based CPU/memory overrides if available.
        """
        token = runner_utils.get_runner_token(self.settings)
        task_def = runner_utils.get_task_definition(self.settings, image_uri, tag)

        container_env = [
            {"name": "RUNNER_REPOSITORY_URL", "value": f"https://github.com/{self.settings.github_repo}"},
            {"name": "RUNNER_TOKEN", "value": token},
            {"name": "RUNNER_LABELS", "value": ",".join(labels)},
            {"name": "RUNNER_NAME", "value": "runner"},
            {"name": "RUNNER_TABLE", "value": self.settings.runner_table},
        ]
        overrides: Dict[str, Any] = {"containerOverrides": [{"name": "runner", "environment": container_env}]}

        # Apply CPU/memory sizing for this runner class, if defined
        sizes = get_class_sizes(self.settings)
        if class_name in sizes:
            cpu = sizes[class_name]["cpu"]
            memory = sizes[class_name]["memory"]
            logger.debug("Applying custom size for %s: cpu=%s, mem=%s", class_name, cpu, memory)
            overrides.update(cpu=str(cpu), memory=str(memory))
            overrides["containerOverrides"][0].update(cpu=cpu, memory=memory)

        logger.info("Running ECS task on cluster %s", self.settings.cluster)
        response = self.ecs.run_task(
            cluster=self.settings.cluster,
            launchType="FARGATE",
            taskDefinition=task_def,
            count=1,
            enableExecuteCommand=True,
            overrides=overrides,
            networkConfiguration={
                "awsvpcConfiguration": {
                    "subnets": self.settings.subnets,
                    "securityGroups": self.settings.security_groups,
                    "assignPublicIp": "ENABLED",
                }
            },
        )

        tasks = response.get("tasks", [])
        if not tasks:
            raise RuntimeError("No tasks were started")

        task_arn = tasks[0]["taskArn"]
        task_id = task_arn.split("/")[-1]
        return task_id
