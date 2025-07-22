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

module "ecs-fleet" {
  source = "./../.."

  github_pat  = "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"
  github_repo = "FonsecaGoncalo/ECS-Runner-Fleet"

  subnet_ids      = module.vpc.public_subnets
  security_groups = [aws_security_group.ecs_tasks_sg.id]
  webhook_secret  = "UM8gRCkLe2TB9O0utuyz2aff+EA8v1DQtxhEgG2UDKXjnkxLBoKFrq0fFD9LNYwhIWCZsKKVOsdXq5EFYWwvbg=="

  extra_runner_images = {
    "python" : "./runners/base_python"
  }

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