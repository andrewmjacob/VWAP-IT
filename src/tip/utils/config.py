from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Core
    TIP_ENV: str = "dev"

    # Postgres
    PG_DSN: str = "postgresql+psycopg://postgres:postgres@localhost:5432/postgres"

    # S3
    S3_BUCKET: str = "tip-dev"
    AWS_REGION: str = "us-east-1"
    AWS_ENDPOINT_URL: str | None = None  # for LocalStack

    # SQS
    SQS_QUEUE_URL: str | None = None
    SQS_DLQ_URL: str | None = None

    # Slack
    SLACK_WEBHOOK_URL: str | None = None
