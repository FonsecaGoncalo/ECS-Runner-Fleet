output "cluster_name" {
  description = "Name of the ECS cluster"
  value       = aws_ecs_cluster.runner_cluster.name
}

output "task_definition_arn" {
  description = "ARN of the default runner task definition"
  value       = aws_ecs_task_definition.runner_task.arn
}

output "extra_task_definition_arns" {
  description = "Map of additional runner task definition ARNs"
  value       = { for k, v in aws_ecs_task_definition.runner_task_extra : k => v.arn }
}

output "repository_url" {
  description = "ECR repository URL for runner images"
  value       = aws_ecr_repository.runner.repository_url
}

output "repository_name" {
  description = "ECR repository name for runner images"
  value       = aws_ecr_repository.runner.name
}
