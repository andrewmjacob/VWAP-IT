output "vpc_id" {
  description = "VPC ID"
  value       = aws_vpc.main.id
}

output "private_subnet_ids" {
  description = "Private subnet IDs"
  value       = aws_subnet.private[*].id
}

output "public_subnet_ids" {
  description = "Public subnet IDs"
  value       = aws_subnet.public[*].id
}

# S3
output "s3_bucket_name" {
  description = "S3 data lake bucket name"
  value       = aws_s3_bucket.data_lake.id
}

output "s3_bucket_arn" {
  description = "S3 data lake bucket ARN"
  value       = aws_s3_bucket.data_lake.arn
}

# SQS
output "sqs_queue_url" {
  description = "SQS events queue URL"
  value       = aws_sqs_queue.events.url
}

output "sqs_queue_arn" {
  description = "SQS events queue ARN"
  value       = aws_sqs_queue.events.arn
}

output "sqs_dlq_url" {
  description = "SQS dead letter queue URL"
  value       = aws_sqs_queue.events_dlq.url
}

# RDS
output "rds_endpoint" {
  description = "RDS endpoint"
  value       = aws_db_instance.main.endpoint
}

output "rds_port" {
  description = "RDS port"
  value       = aws_db_instance.main.port
}

output "db_credentials_secret_arn" {
  description = "Secrets Manager ARN for DB credentials"
  value       = aws_secretsmanager_secret.db_credentials.arn
}

# ECR
output "ecr_repository_url" {
  description = "ECR repository URL"
  value       = aws_ecr_repository.app.repository_url
}

# ECS
output "ecs_cluster_name" {
  description = "ECS cluster name"
  value       = aws_ecs_cluster.main.name
}

output "ecs_cluster_arn" {
  description = "ECS cluster ARN"
  value       = aws_ecs_cluster.main.arn
}

output "wsb_connector_service_name" {
  description = "WSB connector ECS service name"
  value       = aws_ecs_service.wsb_connector.name
}

# CloudWatch
output "cloudwatch_log_group" {
  description = "CloudWatch log group name"
  value       = aws_cloudwatch_log_group.app.name
}

# Observability
output "metrics_alb_dns" {
  description = "Metrics ALB DNS name (if enabled)"
  value       = var.enable_metrics_alb ? aws_lb.metrics[0].dns_name : null
}

output "metrics_endpoint" {
  description = "Prometheus metrics endpoint (if ALB enabled)"
  value       = var.enable_metrics_alb ? "http://${aws_lb.metrics[0].dns_name}/metrics" : null
}

# Useful commands
output "docker_login_command" {
  description = "Command to login to ECR"
  value       = "aws ecr get-login-password --region ${var.aws_region} | docker login --username AWS --password-stdin ${aws_ecr_repository.app.repository_url}"
}

output "docker_push_commands" {
  description = "Commands to build and push Docker image"
  value       = <<-EOT
    docker build -t ${aws_ecr_repository.app.repository_url}:latest .
    docker push ${aws_ecr_repository.app.repository_url}:latest
  EOT
}

