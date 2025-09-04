<div align="center">
  <img alt="AWS Runner Fleet logo" src="/assets/img.png" width="20%" height="20%">

  **AWS Runner Fleet** — Ephemeral GitHub Actions runners on AWS
</div>


---

## Overview

**AWS Runner Fleet** provisions self-hosted GitHub Actions runners as **ephemeral ECS Fargate tasks**.
The control plane reacts to GitHub workflow events, launches runners only when needed, and stops them automatically once the job is complete — providing **isolation, scalability, and cost efficiency**.


## Architecture
<div align="center">
    <img alt="arch" src="/assets/arch.png" width="60%" height="60%">
</div>

The system consists of two main components:

### 1. Control Plane

- **Lambda function** behind **API Gateway** and **EventBridge**:

  * Validates GitHub webhook signatures.
  * Requests short-lived runner registration tokens.
  * Starts ECS Fargate tasks for queued jobs.
  * Updates runner status in DynamoDB.
  * Optionally triggers CodeBuild for on-the-fly runner image builds.

- A scheduled Lambda ("Janitor") periodically scans the runner table and:
  - Stops orphaned ECS tasks and marks runners `OFFLINE`.
  - Fails and cleans up runners stuck in `IMAGE_CREATING`, `STARTING`, or `WAITING_FOR_JOB` beyond a timeout.
  
  Configure via Terraform variables:
  
  - `runner_ttl_seconds` (default: 7200) — global timeout to clean up any runner.
  - `janitor_schedule_expression` (default: `rate(5 minutes)`) — EventBridge schedule.

### 2. ECS Fleet

An **ECS cluster** with:

* IAM roles for execution and runner tasks.
* ECR repository for runner images.
* CloudWatch logging.
* Optional CodeBuild project for dynamic image builds from `image:<base>` labels.

---

### Event Flow Diagram

```mermaid
sequenceDiagram
    participant GitHub
    participant API Gateway
    participant EventBridge
    participant Lambda (Control Plane)
    participant ECS Fargate
    participant DynamoDB
    participant CodeBuild

    GitHub->>API Gateway: workflow_job webhook
    API Gateway->>EventBridge: Forward event
    EventBridge->>Lambda (Control Plane): Trigger
    Lambda (Control Plane)->>GitHub: Request runner token
    alt Image label present
        Lambda (Control Plane)->>CodeBuild: Start image build
        CodeBuild-->>Lambda (Control Plane): Build complete
    end
    Lambda (Control Plane)->>ECS Fargate: Launch task with token
    ECS Fargate->>GitHub: Register as runner
    ECS Fargate-->>GitHub: Run job
    ECS Fargate->>EventBridge: Status update
    EventBridge->>Lambda (Control Plane): Trigger update
    Lambda (Control Plane)->>DynamoDB: Save status
```

### Janitor Cleanup Flow

```mermaid
sequenceDiagram
    participant EB as EventBridge
    participant J as Janitor Lambda
    participant D as DynamoDB
    participant E as ECS

    EB->>J: Scheduled trigger (rate/cron)
    J->>D: Scan runners table
    loop For each runner older than TTL
        alt Has task_id
            J->>E: stop_task(task_id)
            J->>D: Mark state (FAILED if active, else OFFLINE)
        else No task
            J->>D: Mark OFFLINE/FAILED accordingly
        end
    end
```

---

## Runner Lifecycle

- STARTING: created in DynamoDB; awaiting image/task launch.
- IMAGE_CREATING: CodeBuild building a custom image for requested `image:` label.
- WAITING_FOR_JOB: ECS task started; runner registered; waiting for job assignment.
- RUNNING: runner executing a job.
- OFFLINE: task stopped and runner is no longer available.
- FAILED: terminal error (image build failed, task launch failed, or exceeded TTL).

Transitions are persisted in DynamoDB under `status` with timestamps. The Janitor enforces timeouts.

## Terraform Module

All infrastructure is defined in a single Terraform module, composed of:

* `ecs-fleet` — ECS cluster, IAM roles, ECR repo, CloudWatch logs.
* `control-plane` — Lambda orchestration, EventBridge rules, API Gateway.
* (Optional) `image-build-project` — CodeBuild for dynamic runner images.

### Core Variables

| Variable              | Description                                     |
| --------------------- | ----------------------------------------------- |
| `aws_region`          | AWS region for all resources                    |
| `github_pat`          | GitHub PAT for registering runners              |
| `github_repo`         | Repository (`owner/repo`) owning the runners    |
| `webhook_secret`      | Secret for validating GitHub webhooks           |
| `subnet_ids`          | Subnets for Fargate tasks                       |
| `security_groups`     | Security groups for the tasks                   |
| `runner_image_tag`    | Base tag for the runner Docker image            |
| `runner_class_sizes`  | Map of runner sizes (`cpu`, `memory`)           |
| `event_bus_name`      | EventBridge bus name                            |
| `image_build_project` | (Optional) CodeBuild project for dynamic builds |

**Outputs include:**

* Webhook URL for GitHub.
* DynamoDB table name.
* ECS, ECR, and IAM resource ARNs.

---

## Dynamic Images

If `image_build_project` is set, jobs can use:

```yaml
runs-on: [self-hosted, image:ubuntu:22.04]
```

The control plane will:

1. Trigger CodeBuild to build a runner image using [`runner/Dockerfile`](runner/Dockerfile) with the specified base image.
2. Push the image to ECR.
3. Launch a runner task with the built image.

Subsequent jobs reuse the image if it exists.

### Labels

- Required base: `self-hosted`
- Image selection: `image:<base>`, e.g. `image:ubuntu:22.04` or `image:ghcr.io/org/image:tag`
- Class sizing: `class:<name>`, e.g. `class:medium` (maps CPU/memory overrides)

Examples:

```yaml
runs-on: [self-hosted, image:ubuntu:22.04, class:medium]
runs-on: [self-hosted, image:public.ecr.aws/docker/library/node:20, class:large]
```

### Class Sizes (SSM format)

Store CPU/memory overrides as a JSON string in SSM (the module wires the parameter ARN):

```json
{
  "small":  { "cpu": 512,  "memory": 1024 },
  "medium": { "cpu": 1024, "memory": 2048 },
  "large":  { "cpu": 2048, "memory": 4096 }
}
```

---

## CLI Tool

The included CLI (`ecsrunner_cli.py`) lets you inspect runners and class sizes.

Set:

```bash
export RUNNER_TABLE=<dynamodb_table_name>
export CLASS_SIZES_PARAM=<ssm_param_name>
```

### Examples:

```bash
# List all runners
python ecsrunner_cli.py runners list

# Show runner details
python ecsrunner_cli.py runners details <runner_id>

# Terminate a runner by ID
python ecsrunner_cli.py runners terminate <runner_id>

# Show class sizes from SSM
python ecsrunner_cli.py list-class-sizes
```

---

## Getting Started

### 1. Install prerequisites

* [Terraform](https://developer.hashicorp.com/terraform/downloads)
* AWS CLI with credentials configured.
* Python 3.9+.

### 2. Define Terraform module

Create `ecs-fleet.tf` with:

```hcl
module "ecs-fleet" {
  source = "./../.." # path to this module

  github_pat  = "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
  github_repo = "your-github-org/your-repo"

  subnet_ids      = module.vpc.public_subnets
  security_groups = [aws_security_group.ecs_tasks_sg.id]
  webhook_secret  = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

  image_build_project = "image_builder"

  runner_class_sizes = {
    small = {
      cpu    = 512
      memory = 1024
    }
    medium = {
      cpu    = 1024
      memory = 2048
    }
    large = {
      cpu    = 2048
      memory = 4096
    }
  }
}
```

### 3. Install Lambda dependencies

```bash
pip install -r lambda/control_plane/requirements.txt -t lambda/control_plane
```

### 4. Deploy infrastructure

```bash
terraform init
terraform apply
```

### 5. Configure GitHub webhook

* Use the `webhook_url` output from Terraform.
* Event type: `workflow_job`.
* Method: `POST /webhook`.

---

## Example Workflow

```yaml
jobs:
  build:
    runs-on: [self-hosted, class:medium, image:ubuntu:22.04]
    steps:
      - uses: actions/checkout@v4
      - name: Install dependencies
        run: sudo apt-get update && sudo apt-get install -y make
      - name: Run tests
        run: make test
```
