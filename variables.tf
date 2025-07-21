variable "webhook_secret" {
  type      = string
  sensitive = true
}

variable "aws_region" {
  type    = string
  default = "eu-west-3"
}

variable "github_pat" {
  type = string
}

variable "github_repo" {
  type = string
}

variable "runner_image_tag" {
  type        = string
  default     = "12.1"
  description = "Tag used when building and pushing the runner image"
}

variable "extra_runner_images" {
  description = "Map of additional runner labels to Dockerfile directories"
  type        = map(string)
  default     = {}
}

variable "event_bus_name" {
  description = "EventBridge bus name for runner status events"
  type        = string
  default     = "default"
}

variable "subnet_ids" {
  type    = list(string)
  default = []
}

variable "security_groups" {
  type    = list(string)
  default = []
}

variable "runner_class_sizes" {
  description = "Map of runner class sizes and their cpu/memory settings"
  type = map(object({
    cpu    = number
    memory = number
  }))
  default = {
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

variable "event_bus_name" {
  description = "Name of the EventBridge event bus"
  type        = string
  default     = "runner-control-plane"
}




