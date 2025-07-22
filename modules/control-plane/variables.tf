variable "ecs_cluster" {
  description = "ECS cluster name"
  type        = string
}

variable "ecs_subnet_ids" {
  description = "List of subnet IDs for ECS tasks"
  type        = list(string)
}

variable "security_groups" {
  description = "Security groups for ECS tasks"
  type        = list(string)
}

variable "github_pat" {
  description = "GitHub personal access token"
  type        = string
}

variable "github_repo" {
  description = "GitHub repository for runners"
  type        = string
}

variable "webhook_secret" {
  description = "GitHub webhook secret"
  type        = string
}

variable "runner_class_sizes" {
  description = "Map of runner class sizes and their cpu/memory settings"
  type = map(object({
    cpu    = number
    memory = number
  }))
  default = {
    small  = { cpu = 512, memory = 1024 }
    medium = { cpu = 1024, memory = 2048 }
    large  = { cpu = 2048, memory = 4096 }
  }
}

variable "task_definition_arn" {
  description = "ARN of the default runner task definition"
  type        = string
}

variable "label_task_definition_arns" {
  description = "Map of additional runner task definition ARNs by label"
  type        = map(string)
  default     = {}
}

variable "event_bus_name" {
  description = "Name of the EventBridge event bus"
  type        = string
  default     = "runner-control-plane"
}

variable "runner_repository_url" {
  description = "ECR repository URL for runner images"
  type        = string
}

variable "runner_image_tag" {
  description = "Base tag used for runner images"
  type        = string
}

variable "image_build_project" {
  description = "Optional CodeBuild project for dynamic image builds"
  type        = string
  default     = ""
}
