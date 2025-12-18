variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "dev"
}

variable "project_name" {
  description = "Project name used for resource naming"
  type        = string
  default     = "tip"
}

# VPC
variable "vpc_cidr" {
  description = "CIDR block for VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "Availability zones"
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b"]
}

# RDS
variable "db_instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.t3.micro"
}

variable "db_allocated_storage" {
  description = "RDS allocated storage in GB"
  type        = number
  default     = 20
}

variable "db_name" {
  description = "Database name"
  type        = string
  default     = "tip"
}

variable "db_username" {
  description = "Database master username"
  type        = string
  default     = "tip_admin"
}

# ECS
variable "connector_cpu" {
  description = "CPU units for connector task (256 = 0.25 vCPU)"
  type        = number
  default     = 256
}

variable "connector_memory" {
  description = "Memory for connector task in MB"
  type        = number
  default     = 512
}

variable "connector_desired_count" {
  description = "Number of connector tasks to run"
  type        = number
  default     = 1
}

# Optional
variable "slack_webhook_url" {
  description = "Slack webhook URL for alerts (optional)"
  type        = string
  default     = ""
  sensitive   = true
}

# Observability
variable "enable_metrics_alb" {
  description = "Enable ALB for Prometheus metrics scraping"
  type        = bool
  default     = false
}

variable "metrics_allowed_cidrs" {
  description = "CIDR blocks allowed to access metrics endpoint"
  type        = list(string)
  default     = ["10.0.0.0/16"] # VPC CIDR by default
}

variable "alarm_sns_topic_arn" {
  description = "SNS topic ARN for CloudWatch alarms (optional)"
  type        = string
  default     = ""
}

# GitHub Actions
variable "github_repo" {
  description = "GitHub repository in format 'owner/repo' for OIDC trust"
  type        = string
  default     = ""
}

