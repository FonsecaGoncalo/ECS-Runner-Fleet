variable "aws_region" {
  description = "AWS region"
  type        = string
}

variable "github_repo" {
  description = "GitHub repository name"
  type        = string
}

variable "runner_image_tag" {
  description = "Tag for the runner Docker image"
  type        = string
}

variable "runner_image" {
  description = "Optional prebuilt runner image"
  type        = string
  default     = ""
}

variable "extra_runner_images" {
  description = "Map of additional runner image labels to Dockerfile directories"
  type        = map(string)
  default     = {}
}

variable "runner_table_name" {
  description = "Name of the DynamoDB table used to store runner state"
  type        = string
  default     = ""
}

variable "runner_table_arn" {
  description = "ARN of the DynamoDB table used to store runner state"
  type        = string
  default     = ""
}
