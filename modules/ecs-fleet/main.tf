resource "aws_ecs_cluster" "runner_cluster" {
  name = "runner-cluster"
}

resource "aws_cloudwatch_log_group" "ecs_runner" {
  name              = "/ecs/github-runner"
  retention_in_days = 7
}

resource "aws_ecs_task_definition" "runner_task" {
  family                   = "github-runner"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 1024
  memory                   = 2048
  execution_role_arn       = aws_iam_role.task_execution.arn
  task_role_arn            = aws_iam_role.task.arn
  depends_on               = [null_resource.build_runner_image]

  container_definitions = jsonencode([
    {
      name      = "runner"
      image     = local.runner_image
      cpu       = 1024
      memory    = 2048
      essential = true
      environment = [
        { name = "GITHUB_REPO", value = var.github_repo },
        { name = "RUNNER_TABLE", value = var.runner_table_name },
        { name = "ACTIONS_RUNNER_HOOK_JOB_STARTED", value = "/home/runner/job_started.sh" },
        { name = "ACTIONS_RUNNER_HOOK_JOB_COMPLETED", value = "/home/runner/job_completed.sh" }
      ],
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.ecs_runner.name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "runner"
        }
      }
    }
  ])
}

resource "aws_ecs_task_definition" "runner_task_extra" {
  for_each                 = var.extra_runner_images
  family                   = "github-runner-${each.key}"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 1024
  memory                   = 2048
  execution_role_arn       = aws_iam_role.task_execution.arn
  task_role_arn            = aws_iam_role.task.arn
  depends_on               = [null_resource.build_extra_images]

  container_definitions = jsonencode([
    {
      name      = "runner"
      image     = local.label_images[each.key]
      cpu       = 1024
      memory    = 2048
      essential = true
      environment = [
        { name = "GITHUB_REPO", value = var.github_repo },
        { name = "RUNNER_TABLE", value = var.runner_table_name },
        { name = "ACTIONS_RUNNER_HOOK_JOB_STARTED", value = "/home/runner/job_started.sh" },
        { name = "ACTIONS_RUNNER_HOOK_JOB_COMPLETED", value = "/home/runner/job_completed.sh" }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.ecs_runner.name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "runner"
        }
      }
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

resource "aws_iam_role_policy_attachment" "task_execution" {
  role       = aws_iam_role.task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy_attachment" "task_execution_ssm" {
  role       = aws_iam_role.task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_role_policy" "task_dynamodb" {
  name = "task-dynamodb"
  role = aws_iam_role.task.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action   = ["dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:DeleteItem"]
        Effect   = "Allow"
        Resource = [var.runner_table_arn]
      }
    ]
  })
}

data "aws_iam_policy_document" "ecs_task_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}