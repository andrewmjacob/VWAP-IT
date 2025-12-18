# Observability Infrastructure
# Includes metrics server, ALB for scraping, and CloudWatch alarms

# ============================================================================
# Metrics Server Task Definition
# ============================================================================

resource "aws_ecs_task_definition" "metrics_server" {
  family                   = "${var.project_name}-${var.environment}-metrics"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([
    {
      name  = "metrics"
      image = "${aws_ecr_repository.app.repository_url}:latest"

      command = ["serve-metrics", "--host", "0.0.0.0", "--port", "8080"]

      environment = [
        { name = "TIP_ENV", value = var.environment }
      ]

      portMappings = [
        {
          containerPort = 8080
          protocol      = "tcp"
        }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.app.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "metrics"
        }
      }

      essential = true

      healthCheck = {
        command     = ["CMD-SHELL", "curl -f http://localhost:8080/metrics || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 60
      }
    }
  ])

  tags = {
    Name = "${var.project_name}-${var.environment}-metrics"
  }
}

# ============================================================================
# Security Group for Metrics ALB
# ============================================================================

resource "aws_security_group" "metrics_alb" {
  count = var.enable_metrics_alb ? 1 : 0

  name        = "${var.project_name}-${var.environment}-metrics-alb"
  description = "Security group for metrics ALB"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = var.metrics_allowed_cidrs
    description = "HTTP from allowed CIDRs"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
    description = "Allow all outbound"
  }

  tags = {
    Name = "${var.project_name}-${var.environment}-metrics-alb-sg"
  }
}

# Security group rule to allow ALB to reach metrics containers
resource "aws_security_group_rule" "ecs_from_metrics_alb" {
  count = var.enable_metrics_alb ? 1 : 0

  type                     = "ingress"
  from_port                = 8080
  to_port                  = 8080
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.metrics_alb[0].id
  security_group_id        = aws_security_group.ecs_tasks.id
  description              = "Metrics from ALB"
}

# ============================================================================
# Application Load Balancer for Metrics (optional)
# ============================================================================

resource "aws_lb" "metrics" {
  count = var.enable_metrics_alb ? 1 : 0

  name               = "${var.project_name}-${var.environment}-metrics"
  internal           = true # Internal ALB - only accessible within VPC
  load_balancer_type = "application"
  security_groups    = [aws_security_group.metrics_alb[0].id]
  subnets            = aws_subnet.private[*].id

  tags = {
    Name = "${var.project_name}-${var.environment}-metrics-alb"
  }
}

resource "aws_lb_target_group" "metrics" {
  count = var.enable_metrics_alb ? 1 : 0

  name        = "${var.project_name}-${var.environment}-metrics"
  port        = 8080
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip"

  health_check {
    enabled             = true
    healthy_threshold   = 2
    unhealthy_threshold = 3
    timeout             = 5
    interval            = 30
    path                = "/metrics"
    matcher             = "200"
  }

  tags = {
    Name = "${var.project_name}-${var.environment}-metrics-tg"
  }
}

resource "aws_lb_listener" "metrics" {
  count = var.enable_metrics_alb ? 1 : 0

  load_balancer_arn = aws_lb.metrics[0].arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.metrics[0].arn
  }
}

# ============================================================================
# ECS Service for Metrics Server (optional)
# ============================================================================

resource "aws_ecs_service" "metrics" {
  count = var.enable_metrics_alb ? 1 : 0

  name            = "${var.project_name}-${var.environment}-metrics"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.metrics_server.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.metrics[0].arn
    container_name   = "metrics"
    container_port   = 8080
  }

  tags = {
    Name = "${var.project_name}-${var.environment}-metrics"
  }

  # Terraform infers dependency from load_balancer.target_group_arn reference
}

# ============================================================================
# CloudWatch Alarms
# ============================================================================

# Alarm for high error rate in logs
resource "aws_cloudwatch_log_metric_filter" "errors" {
  name           = "${var.project_name}-${var.environment}-errors"
  pattern        = "ERROR"
  log_group_name = aws_cloudwatch_log_group.app.name

  metric_transformation {
    name      = "ErrorCount"
    namespace = "${var.project_name}/${var.environment}"
    value     = "1"
  }
}

resource "aws_cloudwatch_metric_alarm" "high_error_rate" {
  alarm_name          = "${var.project_name}-${var.environment}-high-error-rate"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "ErrorCount"
  namespace           = "${var.project_name}/${var.environment}"
  period              = 300
  statistic           = "Sum"
  threshold           = 10
  alarm_description   = "High error rate detected in application logs"

  alarm_actions = var.alarm_sns_topic_arn != "" ? [var.alarm_sns_topic_arn] : []

  tags = {
    Name = "${var.project_name}-${var.environment}-high-error-rate"
  }
}

# Alarm for SQS DLQ messages (indicates failed processing)
resource "aws_cloudwatch_metric_alarm" "dlq_messages" {
  alarm_name          = "${var.project_name}-${var.environment}-dlq-messages"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 300
  statistic           = "Average"
  threshold           = 0
  alarm_description   = "Messages in DLQ indicate failed event processing"

  dimensions = {
    QueueName = aws_sqs_queue.events_dlq.name
  }

  alarm_actions = var.alarm_sns_topic_arn != "" ? [var.alarm_sns_topic_arn] : []

  tags = {
    Name = "${var.project_name}-${var.environment}-dlq-messages"
  }
}

# Alarm for RDS CPU
resource "aws_cloudwatch_metric_alarm" "rds_cpu" {
  alarm_name          = "${var.project_name}-${var.environment}-rds-high-cpu"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "CPUUtilization"
  namespace           = "AWS/RDS"
  period              = 300
  statistic           = "Average"
  threshold           = 80
  alarm_description   = "RDS CPU utilization is high"

  dimensions = {
    DBInstanceIdentifier = aws_db_instance.main.identifier
  }

  alarm_actions = var.alarm_sns_topic_arn != "" ? [var.alarm_sns_topic_arn] : []

  tags = {
    Name = "${var.project_name}-${var.environment}-rds-high-cpu"
  }
}

# Alarm for RDS free storage
resource "aws_cloudwatch_metric_alarm" "rds_storage" {
  alarm_name          = "${var.project_name}-${var.environment}-rds-low-storage"
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = 1
  metric_name         = "FreeStorageSpace"
  namespace           = "AWS/RDS"
  period              = 300
  statistic           = "Average"
  threshold           = 5368709120 # 5GB in bytes
  alarm_description   = "RDS free storage space is low"

  dimensions = {
    DBInstanceIdentifier = aws_db_instance.main.identifier
  }

  alarm_actions = var.alarm_sns_topic_arn != "" ? [var.alarm_sns_topic_arn] : []

  tags = {
    Name = "${var.project_name}-${var.environment}-rds-low-storage"
  }
}

