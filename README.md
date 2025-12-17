# Trading Intelligence Platform – Foundation v0

Build boring. Build solid. This repository implements the platform backbone for a trading system:
- ingestion → normalization → enrichment → storage → distribution → observability.

Non-goals: no trading, no backtesting, no indicators, no broker integration, no recommendations.

## Components (v0)
- Canonical Event Schema v1 (JSONSchema + Pydantic)
- S3 Data Lake helpers (raw/, events/, enriched/, indexes/)
- Postgres (system of record) with outbox pattern
- SQS Event Bus (with DLQ) + dispatcher
- Connector framework (config-driven) + WSB mock connector
- Enrichment services (LLM annotators only) with cost controls and shadow/emit
- Canary/shadow tracking and promotion rules
- Observability (Prometheus) + Slack alerts/digest
- DuckDB + Parquet analytics (daily indexes + query runner)
- Replay tooling (tsEvent/tsIngested)

## Local Dev
- Docker Compose: Postgres, LocalStack (S3, SQS)
- Bootstrap script creates buckets and queues
- .env.example for configuration

## CI/CD
- PR: lint, tests, schema validation, docker build
- Main: build + push images; deploy to dev (placeholder)

## License
Apache-2.0
