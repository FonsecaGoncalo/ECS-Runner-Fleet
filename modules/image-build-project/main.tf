resource "aws_iam_role" "codebuild" {
  name = "${var.project_name}-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Action    = "sts:AssumeRole",
      Effect    = "Allow",
      Principal = { Service = "codebuild.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "codebuild" {
  role = aws_iam_role.codebuild.name
  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Action = [
          "ecr:GetAuthorizationToken",
          "ecr:BatchCheckLayerAvailability",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage",
          "ecr:InitiateLayerUpload",
          "ecr:UploadLayerPart",
          "ecr:CompleteLayerUpload",
          "ecr:PutImage"
        ],
        Resource = "*"
      },
      {
        Effect = "Allow",
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ],
        Resource = "*"
      },
      {
        Effect   = "Allow",
        Action   = ["s3:GetObject"],
        Resource = "${aws_s3_bucket.runner_source.arn}/*"
      },
      {
        Effect   = "Allow",
        Action   = ["events:PutEvents"],
        Resource = "*"
      }
    ]
  })
}

data "aws_caller_identity" "current" {}

data "archive_file" "runner_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../../runner"
  output_path = "${path.module}/runner.zip"
}

resource "aws_s3_bucket" "runner_source" {
  bucket        = "${data.aws_caller_identity.current.account_id}-runner-src"
  force_destroy = true
}

resource "aws_s3_object" "runner_source" {
  bucket = aws_s3_bucket.runner_source.id
  key    = "runner.zip"
  source = data.archive_file.runner_zip.output_path
  etag   = data.archive_file.runner_zip.output_md5
}

resource "aws_codebuild_project" "builder" {
  name         = var.project_name
  service_role = aws_iam_role.codebuild.arn

  environment {
    compute_type    = "BUILD_GENERAL1_SMALL"
    image           = "aws/codebuild/standard:7.0"
    type            = "LINUX_CONTAINER"
    privileged_mode = true

    dynamic "environment_variable" {
      for_each = var.github_repo == "" ? [] : [1]
      content {
        name  = "GITHUB_REPO"
        value = var.github_repo
      }
    }

    dynamic "environment_variable" {
      for_each = var.github_pat == "" ? [] : [1]
      content {
        name  = "GITHUB_PAT"
        value = var.github_pat
        type  = "PLAINTEXT"
      }
    }

    environment_variable {
      name  = "REPO_URI"
      value = var.ecr_url
    }

    environment_variable {
      name  = "EVENT_BUS_NAME"
      value = var.event_bus_name
    }
  }

  source {
    type      = "S3"
    location  = "${aws_s3_bucket.runner_source.bucket}/runner.zip"
    buildspec = file("${path.module}/buildspec.yml")
  }

  artifacts {
    type = "NO_ARTIFACTS"
  }
}
