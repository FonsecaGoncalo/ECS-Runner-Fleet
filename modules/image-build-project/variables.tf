variable "project_name" {
  description = "Name of the CodeBuild project"
  type        = string
}

variable "github_repo" {
  description = "Repository owning the runners (owner/repo)"
  type        = string
  default     = ""
}

variable "github_pat" {
  description = "GitHub PAT for cloning the repository"
  type        = string
  default     = ""
}
