# Dead Letter Queue
resource "aws_sqs_queue" "events_dlq" {
  name                      = "${var.project_name}-${var.environment}-events-dlq"
  message_retention_seconds = 1209600 # 14 days

  tags = {
    Name = "${var.project_name}-${var.environment}-events-dlq"
  }
}

# Main Events Queue
resource "aws_sqs_queue" "events" {
  name                       = "${var.project_name}-${var.environment}-events"
  visibility_timeout_seconds = 300 # 5 minutes
  message_retention_seconds  = 604800 # 7 days
  receive_wait_time_seconds  = 20 # Long polling

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.events_dlq.arn
    maxReceiveCount     = 5
  })

  tags = {
    Name = "${var.project_name}-${var.environment}-events"
  }
}

# DLQ redrive allow policy
resource "aws_sqs_queue_redrive_allow_policy" "events_dlq" {
  queue_url = aws_sqs_queue.events_dlq.id

  redrive_allow_policy = jsonencode({
    redrivePermission = "byQueue"
    sourceQueueArns   = [aws_sqs_queue.events.arn]
  })
}

