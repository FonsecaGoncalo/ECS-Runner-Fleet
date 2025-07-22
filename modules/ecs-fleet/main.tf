resource "aws_ecs_cluster" "runner_cluster" {
  name = "runner-cluster"
}

resource "aws_cloudwatch_log_group" "ecs_runner" {
  name              = "/ecs/github-runner"
  retention_in_days = 7
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

resource "aws_iam_role_policy" "task_events" {
  name = "task-events"
  role = aws_iam_role.task.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action   = ["events:PutEvents"]
        Effect   = "Allow"
        Resource = "*"
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
