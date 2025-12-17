# AWS Infrastructure for Trading Intelligence Platform

This directory contains Terraform configurations to deploy TIP to AWS.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              VPC (10.0.0.0/16)                           │
│                                                                          │
│  ┌────────────────────┐     ┌────────────────────────────────────────┐  │
│  │   Public Subnets   │     │          Private Subnets               │  │
│  │   (10.0.0.0/24)    │     │         (10.0.10.0/24+)                │  │
│  │                    │     │                                        │  │
│  │  ┌──────────────┐  │     │  ┌──────────────┐  ┌───────────────┐  │  │
│  │  │  NAT Gateway │  │────▶│  │  ECS Fargate │  │  RDS Postgres │  │  │
│  │  └──────────────┘  │     │  │   (Tasks)    │  │    (16.4)     │  │  │
│  │         │          │     │  └──────────────┘  └───────────────┘  │  │
│  │         ▼          │     │         │                  ▲          │  │
│  │  ┌──────────────┐  │     │         │                  │          │  │
│  │  │   Internet   │  │     │         └──────────────────┘          │  │
│  │  │   Gateway    │  │     │                                        │  │
│  │  └──────────────┘  │     └────────────────────────────────────────┘  │
│  └────────────────────┘                                                  │
└─────────────────────────────────────────────────────────────────────────┘
                │
    ┌───────────┼───────────┬───────────────────┐
    ▼           ▼           ▼                   ▼
┌───────┐  ┌───────┐  ┌───────────┐  ┌──────────────────┐
│  S3   │  │  SQS  │  │    ECR    │  │ Secrets Manager  │
│ Bucket│  │+DLQ   │  │ Registry  │  │  (DB Credentials)│
└───────┘  └───────┘  └───────────┘  └──────────────────┘
```

## Resources Created

| Resource | Description |
|----------|-------------|
| VPC | Isolated network with public/private subnets across 2 AZs |
| NAT Gateway | Allows private subnets to access internet |
| VPC Endpoints | S3, SQS, ECR, CloudWatch Logs, Secrets Manager (reduces NAT costs) |
| S3 Bucket | Data lake with lifecycle policies (raw/, events/, enriched/, indexes/) |
| SQS Queues | Events queue + Dead Letter Queue (maxReceiveCount=5) |
| RDS Postgres | PostgreSQL 16.4 with automated backups |
| ECR | Container registry with lifecycle policy |
| ECS Cluster | Fargate cluster with spot capacity |
| ECS Services | WSB connector running continuously |
| IAM Roles | Task execution role + task role with least privilege |
| Secrets Manager | Stores DB credentials securely |
| CloudWatch Logs | Centralized logging for ECS tasks |

## Prerequisites

1. AWS CLI configured with appropriate credentials
2. Terraform >= 1.5 installed
3. Docker installed (for building images)

## Quick Start

### 1. Initialize Terraform

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your settings

terraform init
```

### 2. Deploy Infrastructure

```bash
# Preview changes
terraform plan -out=tfplan

# Apply changes
terraform apply tfplan
```

Or use the Makefile from project root:
```bash
make tf-init
make tf-plan
make tf-apply
```

### 3. Build and Push Docker Image

```bash
# Get ECR login
$(terraform output -raw docker_login_command)

# Build and push
cd ../..
docker build -t $(terraform -chdir=infra/terraform output -raw ecr_repository_url):latest .
docker push $(terraform -chdir=infra/terraform output -raw ecr_repository_url):latest

# Or use the script
./scripts/push-image.sh latest
```

### 4. Run Database Migrations

The RDS instance is in a private subnet. To run migrations, you have options:

**Option A: ECS Run Task (recommended)**
```bash
aws ecs run-task \
  --cluster tip-dev \
  --task-definition tip-dev-wsb-connector \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-xxx],securityGroups=[sg-xxx],assignPublicIp=DISABLED}" \
  --overrides '{"containerOverrides":[{"name":"wsb-connector","command":["python","-c","from tip.db.session import get_engine_sync; import os; engine=get_engine_sync(os.environ[\"PG_DSN\"]); exec(open(\"src/tip/db/migrations/001_init.sql\").read())"]}]}'
```

**Option B: Bastion Host**
Set up a bastion host in the public subnet and tunnel through it.

**Option C: AWS Session Manager**
Use SSM to connect to a running ECS task and run migrations.

### 5. Verify Deployment

```bash
# Check ECS service status
aws ecs describe-services --cluster tip-dev --services tip-dev-wsb-connector

# View logs
aws logs tail /ecs/tip-dev --follow

# Get outputs
terraform output
```

## Updating the Application

```bash
# Build and push new image
./scripts/push-image.sh latest

# Force new deployment
aws ecs update-service --cluster tip-dev --service tip-dev-wsb-connector --force-new-deployment
```

Or use Make:
```bash
make docker-push
make ecs-deploy
```

## Cost Estimation (Dev Environment)

| Resource | Estimated Monthly Cost |
|----------|----------------------|
| NAT Gateway | ~$32 + data transfer |
| RDS db.t3.micro | ~$13 |
| ECS Fargate (0.25 vCPU, 512MB) | ~$9 |
| VPC Endpoints | ~$22 (5 interface endpoints) |
| S3, SQS, CloudWatch | ~$1-5 (usage based) |
| **Total** | **~$80-100/month** |

### Cost Optimization Tips

1. Use `FARGATE_SPOT` for non-critical workloads (already enabled)
2. Consider removing some VPC endpoints if NAT costs are acceptable
3. Scale down `connector_desired_count` to 0 when not in use
4. Use smaller RDS instance for dev

## Cleanup

```bash
terraform destroy
```

⚠️ **Warning**: This will delete all resources including the database and S3 bucket contents.

## Customization

### Production Considerations

For production, update `terraform.tfvars`:

```hcl
environment = "prod"

# RDS - larger instance, multi-AZ
db_instance_class = "db.t3.medium"

# ECS - more resources
connector_cpu    = 512
connector_memory = 1024
connector_desired_count = 2
```

And enable in `rds.tf`:
- `multi_az = true`
- `deletion_protection = true`
- `skip_final_snapshot = false`

### Adding New Services

1. Create new task definition in `ecs.tf`
2. Add IAM policies if needed in `iam.tf`
3. Create ECS service or scheduled task

