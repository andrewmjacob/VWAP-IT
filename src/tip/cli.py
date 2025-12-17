from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
import typer
from tip.utils.config import Settings
from tip.storage.s3 import S3Client, S3Config
from tip.bus.sqs import SQSBus, SQSConfig
from tip.connectors.wsb_mock import WSBMockConnector
from tip.connectors.base import ConnectorConfig

app = typer.Typer(add_completion=False)


@app.command()
def run_wsb(mode: str = typer.Option("shadow", help="shadow or emit")):
    s = Settings()
    s3 = S3Client(S3Config(bucket=s.S3_BUCKET, region=s.AWS_REGION))
    bus = None
    if mode == "emit" and s.SQS_QUEUE_URL:
        bus = SQSBus(SQSConfig(queue_url=s.SQS_QUEUE_URL, dlq_url=s.SQS_DLQ_URL, region=s.AWS_REGION))
    cfg = ConnectorConfig(
        name="wsb-mock",
        mode=mode,
        source="wsb",
        s3_bucket=s.S3_BUCKET,
        dsn=s.PG_DSN,
        sqs_queue_url=s.SQS_QUEUE_URL,
    )
    c = WSBMockConnector(cfg, s3, bus)
    stats = c.run_once()
    typer.echo(json.dumps(stats))


@app.command()
def replay_last_minutes(minutes: int = 60):
    from tip.replay.replay import replay_by_ts_ingested

    s = Settings()
    bus = SQSBus(SQSConfig(queue_url=s.SQS_QUEUE_URL, dlq_url=s.SQS_DLQ_URL, region=s.AWS_REGION))
    end = datetime.now(timezone.utc)
    start = end - timedelta(minutes=minutes)
    cnt = replay_by_ts_ingested(s.PG_DSN, bus, start, end)
    typer.echo(f"Replayed {cnt} events")


if __name__ == "__main__":
    app()
