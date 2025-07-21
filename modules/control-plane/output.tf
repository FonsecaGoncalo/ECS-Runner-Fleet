output "webhook_url" {
  value = aws_apigatewayv2_stage.default.invoke_url
}

output "runner_table_name" {
  value = aws_dynamodb_table.runner_status.name
}

output "runner_table_arn" {
  value = aws_dynamodb_table.runner_status.arn
}
