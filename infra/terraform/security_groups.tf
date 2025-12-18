# Security Group for ECS Tasks (base - no cross-references)
resource "aws_security_group" "ecs_tasks" {
  name        = "${var.project_name}-${var.environment}-ecs-tasks"
  description = "Security group for ECS tasks"
  vpc_id      = aws_vpc.main.id

  # Outbound HTTPS (for AWS APIs via endpoints)
  egress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "HTTPS outbound"
  }

  # Outbound to NAT for external APIs if needed
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
    description = "All outbound via NAT"
  }

  tags = {
    Name = "${var.project_name}-${var.environment}-ecs-tasks-sg"
  }
}

# Security Group for RDS (base - no cross-references)
resource "aws_security_group" "rds" {
  name        = "${var.project_name}-${var.environment}-rds"
  description = "Security group for RDS PostgreSQL"
  vpc_id      = aws_vpc.main.id

  tags = {
    Name = "${var.project_name}-${var.environment}-rds-sg"
  }
}

# Separate rule: Allow ECS tasks to connect to RDS (breaks the cycle)
resource "aws_security_group_rule" "ecs_to_rds" {
  type                     = "egress"
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.rds.id
  security_group_id        = aws_security_group.ecs_tasks.id
  description              = "PostgreSQL to RDS"
}

# Separate rule: Allow RDS to receive from ECS tasks (breaks the cycle)
resource "aws_security_group_rule" "rds_from_ecs" {
  type                     = "ingress"
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.ecs_tasks.id
  security_group_id        = aws_security_group.rds.id
  description              = "PostgreSQL from ECS tasks"
}
