<div align="center">

<picture>
  <source media="(prefers-color-scheme: light)" srcset="/assets/img.png">
  <img alt="aws-runner-fleet logo" src="/assets/img.png" width="25%" height="25%">
</picture>

**AWS Runner Fleet**
</div>

---

ECS Runner Fleet provides ephemeral GitHub Actions self-hosted runners powered by AWS ECS Fargate. Runners are launched on-demand in response to workflow events, allowing teams to scale builds automatically while keeping isolation and cost under control.

## Architecture
The solution is composed of two main parts:

1. **Control plane** – A Lambda function orchestrated through API Gateway and EventBridge. It validates GitHub webhooks, fetches runner tokens and starts ECS tasks. Runner status updates are stored in DynamoDB.
2. **ECS fleet** – A set of Fargate task definitions and an ECS cluster where runner containers execute jobs. Images are built and stored in ECR and can be extended per label.

The event flow is:

- GitHub sends a `workflow_job` webhook when a job is queued.
- API Gateway forwards the event to EventBridge which triggers the control plane Lambda.
- Lambda launches a Fargate task that registers as a runner. When the job finishes the task stops and emits a status event.

## Terraform module
All infrastructure is defined as a Terraform module consisting of two sub-modules: `ecs-fleet` and `control-plane`. The module exposes several inputs to customise the deployment:

| Variable | Description |
|----------|-------------|
| `aws_region` | AWS region for resources |
| `github_pat` | Personal access token used to register runners |
| `github_repo` | Repository owning the runners (`owner/repo`) |
| `webhook_secret` | Secret used to validate GitHub webhooks |
| `subnet_ids` | Subnets where Fargate tasks run |
| `security_groups` | Security groups for the tasks |
| `runner_image_tag` | Tag for the base runner Docker image |
| `extra_runner_images` | Map of labels to Dockerfile paths for additional images |
| `runner_class_sizes` | Map of runner "class" names to CPU and memory settings |
| `event_bus_name` | Name of the EventBridge bus |
| `image_build_project` | Optional name of a CodeBuild project used for dynamic image builds |

The module outputs the webhook URL for GitHub and additional resource identifiers.

If `image_build_project` is set the module also provisions a CodeBuild project with that name.
Jobs can then use labels of the form `image:<base-image>`. When such a job is queued
the control plane triggers the project to build a runner image using [`runner/Dockerfile`](runner/Dockerfile)
but replacing its `FROM` statement with `<base-image>`. After the build completes a temporary
task definition is registered with the new image to run the workflow. Subsequent jobs reuse the built image if it exists in ECR.

Example usage can be found under [`examples/ecs-fleet-example`](examples/ecs-fleet-example).

## CLI tool
`ecsrunner_cli.py` offers convenience commands to inspect running tasks and stored runner data. Set `RUNNER_STATE_TABLE` and `CLASS_SIZES_PARAM` to point at the DynamoDB table and SSM parameter created by the module.

```
python ecsrunner_cli.py runners list
python ecsrunner_cli.py runners details <runner_id>
python ecsrunner_cli.py cluster status <cluster>
python ecsrunner_cli.py list-class-sizes
python ecsrunner_cli.py runs list --runner-id <runner_id>
```

## Getting started
1. Install Terraform and configure AWS credentials.
2. Create a `terraform.tfvars` file defining at minimum `github_pat`, `github_repo`, `webhook_secret`, `subnet_ids` and `security_groups`.
3. Initialise and apply the module:
   ```bash
   terraform init
   terraform apply
   ```
4. Configure the printed `webhook_url` as a GitHub webhook targeting `POST /webhook`.

