This project establishes an automated, scalable solution to deploy GitHub Actions self-hosted runners on AWS Elastic Container Service (ECS). It provides dynamic runner provisioning, security isolation, and cost efficiency by utilizing AWS Lambda, API Gateway, and EventBridge to orchestrate the lifecycle of ECS tasks triggered by GitHub workflow events.

## Objectives
- Automatically provision ECS tasks as self-hosted runners upon receiving GitHub Actions workflow events.
- Minimize operational costs by ensuring ECS runners only run when needed.
- Ensure security and isolation by deploying each job in independent ECS tasks.
- Simplify infrastructure management and deployment through Infrastructure as Code (IaC) with Terraform.
- Provide clear monitoring, logging, and observability using AWS CloudWatch.

## Technical Stack
- **AWS ECS (Fargate)**
- **AWS Lambda (Control Plane)**
- **AWS API Gateway (Webhook ingestion)**
- **AWS EventBridge (Event routing)**
- **GitHub Actions (CI/CD)**
- **Terraform (Infrastructure as Code)**

## Workflow Overview
1. GitHub emits webhook events when workflow jobs are queued.
2. AWS API Gateway securely receives webhook events from GitHub.
3. API Gateway publishes webhook payloads directly to AWS EventBridge.
4. EventBridge routes the events to trigger a Lambda function.
5. Lambda acts as the control plane, orchestrating the creation and lifecycle of ECS Fargate tasks.
6. ECS tasks provisioned dynamically register as GitHub self-hosted runners, execute the assigned workflow jobs, and gracefully terminate upon job completion.

## Security & Observability
- Webhook requests are validated in the Lambda function using the configured webhook secret.
- IAM policies strictly scoped for minimal permissions.
- ECS tasks configured for automatic deregistration and termination upon task completion.
- Detailed logging and monitoring via AWS CloudWatch for operational insights and troubleshooting.

## Deployment
Infrastructure is fully defined and deployed using Terraform scripts, facilitating easy replication and management across environments.

This solution delivers a robust, scalable, and efficient GitHub Actions runner infrastructure suitable for teams aiming to streamline their CI/CD operations securely and cost-effectively.

## Getting Started

1. Ensure Terraform is installed and AWS credentials are configured.
2. Update the variables in `terraform/main.tf` or create a `terraform.tfvars` file with your values. You can specify
   `runner_image_tag` to control which Docker image tag is built and pushed to ECR. The image will
   automatically rebuild and push whenever the Dockerfile or tag changes.
   The `runner_class_sizes` variable defines available runner sizes and is stored
   in SSM for the control plane Lambda and CLI. Include a `class:<name>` label in
   your workflow job to launch a runner with the corresponding size.
3. From the `terraform` directory, run:
   ```bash
   terraform init
   terraform apply
   ```
4. The output includes `webhook_url` which should be configured as a GitHub webhook pointing to `POST /webhook`.

The Lambda function in `lambda/control_plane.py` now inspects incoming webhook events and only starts a runner when a `workflow_job` event with the `queued` action is received. The task launched registers as a self-hosted runner using the official GitHub image.

ECS Exec is enabled when launching the runner tasks. The task execution role
must have the `AmazonSSMManagedInstanceCore` policy attached (included in the
Terraform configuration) so that the `ecsrunner_cli.py runners exec` command can
open an interactive shell inside a running task.

The local machine running the CLI must also have the AWS Session Manager plugin
installed. Follow the instructions in the [Session Manager
documentation](https://docs.aws.amazon.com/console/systems-manager/session-manager-plugin-not-found)
if you encounter a "SessionManagerPlugin is not found" error.

## CLI Utility

This repository also provides `ecsrunner_cli.py`, a small command-line tool for inspecting and managing runners. The DynamoDB table name must be supplied via the `RUNNER_STATE_TABLE` environment variable.

Example usage:

```bash
python ecsrunner_cli.py runners list
python ecsrunner_cli.py runners details <runner_id>
python ecsrunner_cli.py cluster status <cluster>
python ecsrunner_cli.py list-class-sizes
python ecsrunner_cli.py runs list --runner-id <runner_id>
```

