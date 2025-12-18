.PHONY: up bootstrap migrate run-wsb replay test \
        tf-init tf-plan tf-apply tf-destroy tf-output \
        docker-build docker-push ecs-deploy

# ============================================================================
# Local Development
# ============================================================================

up:
	docker compose -f docker/docker-compose.yml up -d

down:
	docker compose -f docker/docker-compose.yml down

bootstrap:
	AWS_REGION=us-east-1 AWS_ENDPOINT_URL=http://localhost:4566 S3_BUCKET=tip-dev \
	SQS_QUEUE_NAME=events_out SQS_DLQ_NAME=events_out_dlq \
	./scripts/bootstrap_local.sh

migrate:
	PG_DSN=postgresql://postgres:postgres@localhost:5432/postgres ./scripts/migrate.sh

run-wsb:
	python -m tip.cli run-wsb --mode shadow

run-wsb-loop:
	python -m tip.cli run-connector-loop --mode shadow --interval 60

run-reddit:
	python -m tip.cli run-reddit --mode shadow --interval 60 --subreddits "wallstreetbets,stocks"

run-edgar:
	python -m tip.cli run-edgar --mode shadow --interval 180 --ciks "320193,789019,1045810"

lookup-cik:
	@read -p "Enter company name or ticker: " query && python -m tip.cli lookup-cik "$$query"

dispatch-outbox:
	python -m tip.cli dispatch-outbox --batch-size 100 --interval 5

serve-metrics:
	python -m tip.cli serve-metrics --port 8080

replay:
	python -m tip.cli replay-last-minutes --minutes 60

test:
	pytest -q

lint:
	ruff check src/
	black --check src/

format:
	ruff check --fix src/
	black src/

# ============================================================================
# AWS Infrastructure (Terraform)
# ============================================================================

tf-init:
	cd infra/terraform && terraform init

tf-plan:
	cd infra/terraform && terraform plan -out=tfplan

tf-apply:
	cd infra/terraform && terraform apply tfplan && rm -f tfplan

tf-destroy:
	cd infra/terraform && terraform destroy

tf-output:
	cd infra/terraform && terraform output

# ============================================================================
# AWS Deployment - High Level Commands
# ============================================================================

## Deploy entire infrastructure from scratch
deploy: 
	@echo "🚀 Deploying TIP Infrastructure to AWS..."
	@echo ""
	@echo "Step 1/4: Initializing Terraform..."
	cd infra/terraform && terraform init
	@echo ""
	@echo "Step 2/4: Planning infrastructure..."
	cd infra/terraform && terraform plan -out=tfplan
	@echo ""
	@echo "Step 3/4: Applying infrastructure..."
	cd infra/terraform && terraform apply tfplan && rm -f tfplan
	@echo ""
	@echo "Step 4/4: Building and pushing Docker image..."
	$(MAKE) docker-build-amd64
	$(MAKE) docker-push
	@echo ""
	@echo "✅ Deployment complete!"
	@echo ""
	cd infra/terraform && terraform output

## Teardown all infrastructure (DESTRUCTIVE - data will be lost!)
teardown:
	@echo "⚠️  WARNING: This will DESTROY all AWS infrastructure!"
	@echo "   - RDS database and all data"
	@echo "   - S3 buckets and all stored events"
	@echo "   - SQS queues and pending messages"
	@echo "   - ECS services and tasks"
	@echo ""
	@read -p "Type 'destroy' to confirm: " confirm && [ "$$confirm" = "destroy" ] || (echo "Aborted." && exit 1)
	@echo ""
	@echo "🔥 Destroying infrastructure..."
	cd infra/terraform && terraform destroy -auto-approve
	@echo ""
	@echo "✅ Teardown complete. All resources destroyed."

## Pause infrastructure (stop ECS, keep data) - saves ~$50/mo
pause:
	@echo "⏸️  Pausing ECS services (keeping infrastructure)..."
	aws ecs update-service --cluster tip-dev --service tip-dev-wsb-connector --desired-count 0 --no-cli-pager || true
	aws ecs update-service --cluster tip-dev --service tip-dev-outbox-dispatcher --desired-count 0 --no-cli-pager || true
	aws ecs update-service --cluster tip-dev --service tip-dev-metrics --desired-count 0 --no-cli-pager || true
	aws ecs update-service --cluster tip-dev --service tip-dev-reddit-connector --desired-count 0 --no-cli-pager || true
	aws ecs update-service --cluster tip-dev --service tip-dev-edgar-connector --desired-count 0 --no-cli-pager || true
	@echo ""
	@echo "✅ Services paused. Data preserved. Run 'make resume' to restart."

## Resume paused infrastructure
resume:
	@echo "▶️  Resuming ECS services..."
	aws ecs update-service --cluster tip-dev --service tip-dev-wsb-connector --desired-count 1 --no-cli-pager || true
	aws ecs update-service --cluster tip-dev --service tip-dev-outbox-dispatcher --desired-count 1 --no-cli-pager || true
	aws ecs update-service --cluster tip-dev --service tip-dev-metrics --desired-count 1 --no-cli-pager || true
	aws ecs update-service --cluster tip-dev --service tip-dev-reddit-connector --desired-count 1 --no-cli-pager || true
	aws ecs update-service --cluster tip-dev --service tip-dev-edgar-connector --desired-count 1 --no-cli-pager || true
	@echo ""
	@echo "✅ Services resumed."

## Show current infrastructure status
status:
	@echo "📊 TIP Infrastructure Status"
	@echo "============================"
	@echo ""
	@echo "ECS Services:"
	@aws ecs list-services --cluster tip-dev --query 'serviceArns[*]' --output table --no-cli-pager 2>/dev/null || echo "  (cluster not found)"
	@echo ""
	@echo "RDS Instance:"
	@aws rds describe-db-instances --query 'DBInstances[?DBInstanceIdentifier==`tip-dev`].[DBInstanceIdentifier,DBInstanceStatus,Endpoint.Address]' --output table --no-cli-pager 2>/dev/null || echo "  (not found)"
	@echo ""
	@echo "S3 Bucket:"
	@aws s3 ls s3://tip-dev-data-lake --summarize --human-readable 2>/dev/null | tail -2 || echo "  (not found)"

# ============================================================================
# Docker Commands
# ============================================================================

docker-build:
	docker build -t tip:latest .

docker-build-amd64:
	docker buildx build --platform linux/amd64 -t tip:latest --load .

docker-push:
	./scripts/push-image.sh latest

ecs-deploy:
	@echo "Forcing new deployment of ECS services..."
	aws ecs update-service --cluster tip-dev --service tip-dev-wsb-connector --force-new-deployment --no-cli-pager

migrate-aws:
	./scripts/run-migration-aws.sh

# ============================================================================
# Help
# ============================================================================

help:
	@echo "TIP Makefile Commands"
	@echo "====================="
	@echo ""
	@echo "Infrastructure:"
	@echo "  make deploy    - Deploy entire AWS infrastructure from scratch"
	@echo "  make teardown  - Destroy all AWS infrastructure (DESTRUCTIVE)"
	@echo "  make pause     - Stop ECS services, keep data (~saves \$$50/mo)"
	@echo "  make resume    - Restart paused ECS services"
	@echo "  make status    - Show current infrastructure status"
	@echo ""
	@echo "Development:"
	@echo "  make up        - Start local dev environment (Docker)"
	@echo "  make down      - Stop local dev environment"
	@echo "  make test      - Run tests"
	@echo "  make lint      - Run linters"
	@echo ""
	@echo "Connectors:"
	@echo "  make run-wsb      - Run WSB mock connector locally"
	@echo "  make run-reddit   - Run Reddit connector locally"
	@echo "  make run-edgar    - Run SEC EDGAR connector locally"
	@echo "  make lookup-cik   - Look up CIK for a company"
	@echo ""
	@echo "Services:"
	@echo "  make dispatch-outbox - Run outbox dispatcher"
	@echo "  make serve-metrics   - Run metrics server"
