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

variable "ecs_cluster" {
  description = "Ecs cluster Name"
  type        = string
}

variable "ecs_subnet_ids" {
  description = "Ecs subnet ids"
  type = list(string)
}

variable "" {}