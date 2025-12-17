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
# AWS Deployment
# ============================================================================

docker-build:
	docker build -t tip:latest .

docker-push:
	./scripts/push-image.sh latest

ecs-deploy:
	@echo "Forcing new deployment of ECS services..."
	aws ecs update-service --cluster tip-dev --service tip-dev-wsb-connector --force-new-deployment

migrate-aws:
	./scripts/run-migration-aws.sh
