.PHONY: up bootstrap migrate run-wsb replay test

up:
	docker compose -f docker/docker-compose.yml up -d

bootstrap:
	AWS_REGION=us-east-1 AWS_ENDPOINT_URL=http://localhost:4566 S3_BUCKET=tip-dev \
	SQS_QUEUE_NAME=events_out SQS_DLQ_NAME=events_out_dlq \
	./scripts/bootstrap_local.sh

migrate:
	PG_DSN=postgresql://postgres:postgres@localhost:5432/postgres ./scripts/migrate.sh

run-wsb:
	python -m tip.cli run-wsb --mode shadow

replay:
	python -m tip.cli replay-last-minutes --minutes 60

test:
	pytest -q
