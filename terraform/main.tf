terraform {
  required_version = ">= 1.0.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  backend "s3" {
    region = "eu-west-3"
    bucket = "tf-state-889194953189"
    key    = "ecs-runner-fleet"
  }
}

provider "aws" {
  region = var.aws_region
}

variable "webhook_secret" {
  type      = string
  sensitive = true
  default   = "UM8gRCkLe2TB9O0utuyz2aff+EA8v1DQtxhEgG2UDKXjnkxLBoKFrq0fFD9LNYwhIWCZsKKVOsdXq5EFYWwvbg=="
}

variable "aws_region" {
  type    = string
  default = "eu-west-3"
}

variable "github_pat" {
  type    = string
  default = "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"
}

variable "github_repo" {
  type    = string
  default = "FonsecaGoncalo/ECS-Runner-Fleet"
}

variable "runner_image" {
  type    = string
  default = ""
  # default = "ghcr.io/actions/actions-runner:latest"
}

variable "subnet_ids" {
  type = list(string)
  default = []
}

variable "security_groups" {
  type = list(string)
  default = []
}

locals {
  runner_image = var.runner_image != "" ? var.runner_image : "${aws_ecr_repository.runner.repository_url}:latest"
}

resource "aws_iam_role" "lambda" {
  name               = "runner-control-plane"
  assume_role_policy = data.aws_iam_policy_document.lambda_trust.json
}

data "aws_iam_policy_document" "lambda_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role_policy" "lambda_policy" {
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.lambda_policy.json
}

data "aws_iam_policy_document" "lambda_policy" {
  statement {
    actions = [
      "ecs:RunTask",
      "ecs:DescribeTasks",
      "iam:PassRole"
    ]
    resources = ["*"]
  }

  statement {
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents"
    ]
    resources = ["*"]
  }
}

resource "aws_lambda_permission" "allow_apigw" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.control_plane.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.webhook_api.execution_arn}/*/*"
}

resource "aws_lambda_function" "control_plane" {
  filename         = data.archive_file.lambda_zip.output_path
  function_name    = "runner-control-plane"
  role             = aws_iam_role.lambda.arn
  handler          = "control_plane.lambda_handler"
  runtime          = "python3.12"
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256

  environment {
    variables = {
      CLUSTER               = aws_ecs_cluster.runner_cluster.name
      TASK_DEFINITION = aws_ecs_task_definition.runner_task.arn
      # SUBNETS = join(",", var.subnet_ids)
      SUBNETS = join(",", module.vpc.public_subnets)
      # SECURITY_GROUPS = join(",", var.security_groups)
       SECURITY_GROUPS = join(",", [aws_security_group.ecs_tasks_sg.id])
      GITHUB_PAT            = var.github_pat
      GITHUB_WEBHOOK_SECRET = var.webhook_secret
    }
  }
}

data "archive_file" "lambda_zip" {
  type        = "zip"
  source_dir  = "../lambda"
  output_path = "../lambda.zip"
}

resource "aws_ecr_repository" "runner" {
  name = "github-runner"
}

resource "null_resource" "build_runner_image" {
  provisioner "local-exec" {
    command = <<EOT
    aws ecr get-login-password --region ${var.aws_region} | docker login --username AWS --password-stdin ${aws_ecr_repository.runner.repository_url}
    docker build -t ${aws_ecr_repository.runner.repository_url}:latest ..
    docker push ${aws_ecr_repository.runner.repository_url}:latest
    EOT
    interpreter = ["bash", "-c"]
  }
}

resource "aws_ecs_cluster" "runner_cluster" {
  name = "runner-cluster"
}

resource "aws_ecs_task_definition" "runner_task" {
  family             = "github-runner"
  requires_compatibilities = ["FARGATE"]
  network_mode       = "awsvpc"
  cpu                = 1024
  memory             = 2048
  execution_role_arn = aws_iam_role.task_execution.arn
  task_role_arn      = aws_iam_role.task.arn
  depends_on = [null_resource.build_runner_image]

  container_definitions = jsonencode([
    {
      name      = "runner"
      image     = local.runner_image
      cpu       = 1024
      memory    = 2048
      essential = true
      environment = [
        { name = "GITHUB_REPO", value = var.github_repo }
      ]
    }
  ])
}

resource "aws_iam_role" "task_execution" {
  name               = "runner-task-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_task_trust.json
}

resource "aws_iam_role" "task" {
  name               = "runner-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_task_trust.json
}

data "aws_iam_policy_document" "ecs_task_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role_policy_attachment" "task_execution" {
  role       = aws_iam_role.task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_apigatewayv2_api" "webhook_api" {
  name          = "github-webhook"
  protocol_type = "HTTP"
}

resource "aws_apigatewayv2_integration" "lambda" {
  api_id                 = aws_apigatewayv2_api.webhook_api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.control_plane.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "webhook" {
  api_id    = aws_apigatewayv2_api.webhook_api.id
  route_key = "POST /webhook"
  target    = "integrations/${aws_apigatewayv2_integration.lambda.id}"
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.webhook_api.id
  name        = "$default"
  auto_deploy = true
}

output "webhook_url" {
  value = aws_apigatewayv2_stage.default.invoke_url
}
