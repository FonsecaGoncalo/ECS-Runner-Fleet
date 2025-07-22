output "cluster_name" {
  description = "Name of the ECS cluster"
  value       = aws_ecs_cluster.runner_cluster.name
}


output "repository_url" {
  description = "ECR repository URL for runner images"
  value       = aws_ecr_repository.runner.repository_url
}

output "repository_name" {
  description = "ECR repository name for runner images"
  value       = aws_ecr_repository.runner.name
}

output "execution_role_arn" {
  description = "ARN of the ECS task execution role"
  value       = aws_iam_role.task_execution.arn
}

output "task_role_arn" {
  description = "ARN of the ECS task role"
  value       = aws_iam_role.task.arn
}

output "log_group_name" {
  description = "Name of the CloudWatch log group for runner tasks"
  value       = aws_cloudwatch_log_group.ecs_runner.name
}
