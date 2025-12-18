# ECS Cluster
resource "aws_ecs_cluster" "main" {
  name = "${var.project_name}-${var.environment}"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = {
    Name = "${var.project_name}-${var.environment}"
  }
}

resource "aws_ecs_cluster_capacity_providers" "main" {
  cluster_name = aws_ecs_cluster.main.name

  capacity_providers = ["FARGATE", "FARGATE_SPOT"]

  default_capacity_provider_strategy {
    base              = 1
    weight            = 100
    capacity_provider = "FARGATE_SPOT" # Use spot for cost savings in dev
  }
}

# CloudWatch Log Group
resource "aws_cloudwatch_log_group" "app" {
  name              = "/ecs/${var.project_name}-${var.environment}"
  retention_in_days = 30

  tags = {
    Name = "${var.project_name}-${var.environment}"
  }
}

# Task Definition for WSB Connector (runs in a loop)
resource "aws_ecs_task_definition" "wsb_connector" {
  family                   = "${var.project_name}-${var.environment}-wsb-connector"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.connector_cpu
  memory                   = var.connector_memory
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([
    {
      name  = "wsb-connector"
      image = "${aws_ecr_repository.app.repository_url}:latest"

      # Use the new continuous loop command
      command = ["run-connector-loop", "--mode", "emit", "--interval", "60"]

      environment = [
        { name = "TIP_ENV", value = var.environment },
        { name = "AWS_REGION", value = var.aws_region },
        { name = "S3_BUCKET", value = aws_s3_bucket.data_lake.id },
        { name = "SQS_QUEUE_URL", value = aws_sqs_queue.events.url },
        { name = "SQS_DLQ_URL", value = aws_sqs_queue.events_dlq.url },
        { name = "SLACK_WEBHOOK_URL", value = var.slack_webhook_url }
      ]

      secrets = [
        {
          name      = "PG_DSN"
          valueFrom = "${aws_secretsmanager_secret.db_credentials.arn}:dsn::"
        }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.app.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "wsb-connector"
        }
      }

      essential = true
    }
  ])

  tags = {
    Name = "${var.project_name}-${var.environment}-wsb-connector"
  }
}

# ECS Service for WSB Connector (runs continuously)
resource "aws_ecs_service" "wsb_connector" {
  name            = "${var.project_name}-${var.environment}-wsb-connector"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.wsb_connector.arn
  desired_count   = var.connector_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = false
  }

  # Allow external changes to desired_count without Terraform plan difference
  lifecycle {
    ignore_changes = [desired_count]
  }

  tags = {
    Name = "${var.project_name}-${var.environment}-wsb-connector"
  }

  depends_on = [
    aws_db_instance.main,
    aws_iam_role_policy.ecs_task_s3,
    aws_iam_role_policy.ecs_task_sqs
  ]
}

# Task Definition for Outbox Dispatcher (runs continuously)
resource "aws_ecs_task_definition" "outbox_dispatcher" {
  family                   = "${var.project_name}-${var.environment}-outbox-dispatcher"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.connector_cpu
  memory                   = var.connector_memory
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([
    {
      name  = "outbox-dispatcher"
      image = "${aws_ecr_repository.app.repository_url}:latest"

      # Use the new dispatch-outbox CLI command (runs continuously)
      command = ["dispatch-outbox", "--batch-size", "100", "--interval", "5"]

      environment = [
        { name = "TIP_ENV", value = var.environment },
        { name = "AWS_REGION", value = var.aws_region },
        { name = "S3_BUCKET", value = aws_s3_bucket.data_lake.id },
        { name = "SQS_QUEUE_URL", value = aws_sqs_queue.events.url },
        { name = "SQS_DLQ_URL", value = aws_sqs_queue.events_dlq.url }
      ]

      secrets = [
        {
          name      = "PG_DSN"
          valueFrom = "${aws_secretsmanager_secret.db_credentials.arn}:dsn::"
        }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.app.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "outbox-dispatcher"
        }
      }

      essential = true
    }
  ])

  tags = {
    Name = "${var.project_name}-${var.environment}-outbox-dispatcher"
  }
}

# ECS Service for Outbox Dispatcher (runs continuously)
resource "aws_ecs_service" "outbox_dispatcher" {
  name            = "${var.project_name}-${var.environment}-outbox-dispatcher"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.outbox_dispatcher.arn
  desired_count   = var.connector_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = false
  }

  lifecycle {
    ignore_changes = [desired_count]
  }

  tags = {
    Name = "${var.project_name}-${var.environment}-outbox-dispatcher"
  }

  depends_on = [
    aws_db_instance.main,
    aws_iam_role_policy.ecs_task_sqs
  ]
}

# ============================================================================
# Reddit Connector (optional)
# ============================================================================

resource "aws_ecs_task_definition" "reddit_connector" {
  count = var.enable_reddit_connector ? 1 : 0

  family                   = "${var.project_name}-${var.environment}-reddit-connector"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.connector_cpu
  memory                   = var.connector_memory
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([
    {
      name  = "reddit-connector"
      image = "${aws_ecr_repository.app.repository_url}:latest"

      command = [
        "run-reddit",
        "--mode", "emit",
        "--interval", "60",
        "--subreddits", var.reddit_subreddits
      ]

      environment = [
        { name = "TIP_ENV", value = var.environment },
        { name = "AWS_REGION", value = var.aws_region },
        { name = "S3_BUCKET", value = aws_s3_bucket.data_lake.id },
        { name = "SQS_QUEUE_URL", value = aws_sqs_queue.events.url },
        { name = "SQS_DLQ_URL", value = aws_sqs_queue.events_dlq.url }
      ]

      secrets = [
        {
          name      = "PG_DSN"
          valueFrom = "${aws_secretsmanager_secret.db_credentials.arn}:dsn::"
        }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.app.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "reddit-connector"
        }
      }

      essential = true
    }
  ])

  tags = {
    Name = "${var.project_name}-${var.environment}-reddit-connector"
  }
}

resource "aws_ecs_service" "reddit_connector" {
  count = var.enable_reddit_connector ? 1 : 0

  name            = "${var.project_name}-${var.environment}-reddit-connector"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.reddit_connector[0].arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = false
  }

  lifecycle {
    ignore_changes = [desired_count]
  }

  tags = {
    Name = "${var.project_name}-${var.environment}-reddit-connector"
  }

  depends_on = [
    aws_db_instance.main,
    aws_iam_role_policy.ecs_task_s3,
    aws_iam_role_policy.ecs_task_sqs
  ]
}

# ============================================================================
# EDGAR Connector (optional)
# ============================================================================

resource "aws_ecs_task_definition" "edgar_connector" {
  count = var.enable_edgar_connector && var.edgar_ciks != "" ? 1 : 0

  family                   = "${var.project_name}-${var.environment}-edgar-connector"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.connector_cpu
  memory                   = var.connector_memory
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([
    {
      name  = "edgar-connector"
      image = "${aws_ecr_repository.app.repository_url}:latest"

      command = [
        "run-edgar",
        "--mode", "emit",
        "--interval", tostring(var.edgar_poll_interval),
        "--ciks", var.edgar_ciks,
        "--max-rps", tostring(var.edgar_max_rps),
        "--user-agent-name", var.edgar_user_agent_name,
        "--user-agent-email", var.edgar_user_agent_email,
        "--state-db", "/tmp/edgar_state.db"
      ]

      environment = [
        { name = "TIP_ENV", value = var.environment },
        { name = "AWS_REGION", value = var.aws_region },
        { name = "S3_BUCKET", value = aws_s3_bucket.data_lake.id },
        { name = "SQS_QUEUE_URL", value = aws_sqs_queue.events.url },
        { name = "SQS_DLQ_URL", value = aws_sqs_queue.events_dlq.url }
      ]

      secrets = [
        {
          name      = "PG_DSN"
          valueFrom = "${aws_secretsmanager_secret.db_credentials.arn}:dsn::"
        }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.app.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "edgar-connector"
        }
      }

      essential = true

      # Mount EFS for persistent state (optional, can use S3 instead)
      # For now, state resets on task restart - acceptable for polling
    }
  ])

  tags = {
    Name = "${var.project_name}-${var.environment}-edgar-connector"
  }
}

resource "aws_ecs_service" "edgar_connector" {
  count = var.enable_edgar_connector && var.edgar_ciks != "" ? 1 : 0

  name            = "${var.project_name}-${var.environment}-edgar-connector"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.edgar_connector[0].arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = false
  }

  lifecycle {
    ignore_changes = [desired_count]
  }

  tags = {
    Name = "${var.project_name}-${var.environment}-edgar-connector"
  }

  depends_on = [
    aws_db_instance.main,
    aws_iam_role_policy.ecs_task_s3,
    aws_iam_role_policy.ecs_task_sqs
  ]
}

