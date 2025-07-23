resource "aws_dynamodb_table" "runner_status" {
  name         = "runner-status"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "runner_id"
  range_key    = "item_id"

  attribute {
    name = "runner_id"
    type = "S"
  }

  attribute {
    name = "item_id"
    type = "S"
  }
}

resource "aws_cloudwatch_event_bus" "control_plane" {
  name = var.event_bus_name
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
      "ecs:StopTask",
      "ecs:RunTask",
      "ecs:DescribeTasks",
      "ecs:DescribeTaskDefinition",
      "ecs:RegisterTaskDefinition",
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

  statement {
    actions = [
      "dynamodb:GetItem",
      "dynamodb:Query",
      "dynamodb:Scan",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem"
    ]
    resources = [aws_dynamodb_table.runner_status.arn]
  }

  statement {
    actions = ["ssm:GetParameter"]
    resources = [aws_ssm_parameter.class_sizes.arn]
  }

  statement {
    actions = ["ecr:DescribeImages"]
    resources = ["*"]
  }

  statement {
    actions = ["codebuild:StartBuild"]
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

resource "aws_cloudwatch_event_rule" "runner_status" {
  name           = "runner-status"
  event_bus_name = var.event_bus_name
  event_pattern = jsonencode({
    source = ["ecs-runner"],
    detail-type = ["runner-status"]
  })
}

resource "aws_cloudwatch_event_rule" "image_build" {
  name           = "image-build"
  event_bus_name = var.event_bus_name
  event_pattern = jsonencode({
    source = ["ecs-runner"],
    detail-type = ["image-build"]
  })
}

resource "aws_cloudwatch_event_target" "runner_status" {
  rule           = aws_cloudwatch_event_rule.runner_status.name
  event_bus_name = var.event_bus_name
  target_id      = "control-plane"
  arn            = aws_lambda_function.control_plane.arn
}

resource "aws_cloudwatch_event_target" "image_build" {
  rule           = aws_cloudwatch_event_rule.image_build.name
  event_bus_name = var.event_bus_name
  target_id      = "control-plane-image-build"
  arn            = aws_lambda_function.control_plane.arn
}

resource "aws_lambda_permission" "allow_events" {
  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.control_plane.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.runner_status.arn
}

resource "aws_lambda_permission" "allow_image_events" {
  statement_id  = "AllowEventBridgeInvokeImage"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.control_plane.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.image_build.arn
}


data "archive_file" "lambda_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../../lambda/control_plane"
  output_path = "../lambda.zip"
}

resource "aws_ssm_parameter" "class_sizes" {
  name = "/ecs-runner/class-sizes"
  type = "String"
  value = jsonencode(var.runner_class_sizes)
}

resource "aws_lambda_function" "control_plane" {
  filename         = data.archive_file.lambda_zip.output_path
  function_name    = "runner-control-plane"
  role             = aws_iam_role.lambda.arn
  handler          = "handler.lambda_handler"
  runtime          = "python3.12"
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256

  environment {
    variables = {
      CLUSTER               = var.ecs_cluster
      SUBNETS = join(",", var.ecs_subnet_ids)
      SECURITY_GROUPS = join(",", var.security_groups)
      GITHUB_PAT            = var.github_pat
      GITHUB_REPO           = var.github_repo
      GITHUB_WEBHOOK_SECRET = var.webhook_secret
      RUNNER_TABLE          = aws_dynamodb_table.runner_status.name
      CLASS_SIZES_PARAM     = aws_ssm_parameter.class_sizes.name
      RUNNER_REPOSITORY_URL = var.runner_repository_url
      RUNNER_IMAGE_TAG      = var.runner_image_tag
      IMAGE_BUILD_PROJECT   = var.image_build_project
      EXECUTION_ROLE_ARN    = var.execution_role_arn
      TASK_ROLE_ARN         = var.task_role_arn
      LOG_GROUP_NAME        = var.log_group_name
      EVENT_BUS_NAME        = var.event_bus_name
    }
  }
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
