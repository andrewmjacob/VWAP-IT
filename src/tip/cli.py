from __future__ import annotations

import json
import time
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
    """Run the WSB mock connector once."""
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
    """Replay events from the last N minutes to SQS."""
    from tip.replay.replay import replay_by_ts_ingested

    s = Settings()
    bus = SQSBus(SQSConfig(queue_url=s.SQS_QUEUE_URL, dlq_url=s.SQS_DLQ_URL, region=s.AWS_REGION))
    end = datetime.now(timezone.utc)
    start = end - timedelta(minutes=minutes)
    cnt = replay_by_ts_ingested(s.PG_DSN, bus, start, end)
    typer.echo(f"Replayed {cnt} events")


@app.command()
def dispatch_outbox(
    batch_size: int = typer.Option(100, help="Number of messages to dispatch per batch"),
    interval: int = typer.Option(5, help="Seconds between dispatch cycles (0 for one-shot)"),
    max_cycles: int = typer.Option(0, help="Max cycles to run (0 for infinite)"),
):
    """Dispatch pending outbox messages to SQS.
    
    Runs continuously by default, dispatching unpublished events from the outbox
    table to SQS. Use --interval=0 for one-shot mode.
    """
    from tip.bus.outbox_dispatcher import dispatch_once

    s = Settings()
    if not s.SQS_QUEUE_URL:
        typer.echo("Error: SQS_QUEUE_URL not configured", err=True)
        raise typer.Exit(1)

    bus = SQSBus(SQSConfig(queue_url=s.SQS_QUEUE_URL, dlq_url=s.SQS_DLQ_URL, region=s.AWS_REGION))
    
    cycles = 0
    total_dispatched = 0
    
    typer.echo(f"Starting outbox dispatcher (batch_size={batch_size}, interval={interval}s)")
    
    while True:
        try:
            dispatched = dispatch_once(s.PG_DSN, bus, batch_size=batch_size)
            total_dispatched += dispatched
            cycles += 1
            
            if dispatched > 0:
                typer.echo(f"[{datetime.now(timezone.utc).isoformat()}] Dispatched {dispatched} messages (total: {total_dispatched})")
            
            # One-shot mode
            if interval == 0:
                break
            
            # Max cycles limit
            if max_cycles > 0 and cycles >= max_cycles:
                typer.echo(f"Reached max cycles ({max_cycles}), exiting")
                break
            
            time.sleep(interval)
            
        except KeyboardInterrupt:
            typer.echo(f"\nShutting down. Total dispatched: {total_dispatched}")
            break
        except Exception as e:
            typer.echo(f"Error during dispatch: {e}", err=True)
            if interval == 0:
                raise typer.Exit(1)
            time.sleep(interval)  # Back off on error
    
    typer.echo(json.dumps({"cycles": cycles, "total_dispatched": total_dispatched}))


@app.command()
def serve_metrics(
    host: str = typer.Option("0.0.0.0", help="Host to bind to"),
    port: int = typer.Option(8080, help="Port to bind to"),
):
    """Run the Prometheus metrics server."""
    import uvicorn
    from tip.observability.server import app as metrics_app
    
    typer.echo(f"Starting metrics server on {host}:{port}")
    uvicorn.run(metrics_app, host=host, port=port, log_level="info")


@app.command()
def migrate():
    """Run database migrations."""
    from pathlib import Path
    from sqlalchemy import create_engine, text
    
    s = Settings()
    if not s.PG_DSN:
        typer.echo("Error: PG_DSN not configured", err=True)
        raise typer.Exit(1)
    
    typer.echo(f"Connecting to database...")
    engine = create_engine(s.PG_DSN)
    
    migrations_dir = Path(__file__).parent / "db" / "migrations"
    migration_files = sorted(migrations_dir.glob("*.sql"))
    
    with engine.begin() as conn:
        for migration_file in migration_files:
            typer.echo(f"Running migration: {migration_file.name}")
            sql = migration_file.read_text()
            conn.execute(text(sql))
            typer.echo(f"  ✓ {migration_file.name} completed")
    
    typer.echo("All migrations completed successfully!")


@app.command()
def run_connector_loop(
    mode: str = typer.Option("shadow", help="shadow or emit"),
    interval: int = typer.Option(60, help="Seconds between connector runs"),
):
    """Run the WSB connector in a continuous loop.
    
    This is the production entrypoint that runs the connector repeatedly
    with the specified interval between runs.
    """
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
    
    typer.echo(f"Starting connector loop (mode={mode}, interval={interval}s)")
    
    while True:
        try:
            stats = c.run_once()
            typer.echo(f"[{datetime.now(timezone.utc).isoformat()}] {json.dumps(stats)}")
            time.sleep(interval)
        except KeyboardInterrupt:
            typer.echo("\nShutting down connector")
            break
        except Exception as e:
            typer.echo(f"Error during connector run: {e}", err=True)
            time.sleep(interval)  # Back off on error


@app.command()
def run_reddit(
    mode: str = typer.Option("shadow", help="shadow or emit"),
    interval: int = typer.Option(60, help="Seconds between connector runs"),
    subreddits: str = typer.Option("wallstreetbets", help="Comma-separated subreddits"),
):
    """Run the Reddit connector in a continuous loop.
    
    Fetches posts from specified subreddits (default: r/wallstreetbets)
    and extracts stock mentions.
    """
    from tip.connectors.reddit import RedditConnector
    
    s = Settings()
    s3 = S3Client(S3Config(bucket=s.S3_BUCKET, region=s.AWS_REGION))
    bus = None
    if mode == "emit" and s.SQS_QUEUE_URL:
        bus = SQSBus(SQSConfig(queue_url=s.SQS_QUEUE_URL, dlq_url=s.SQS_DLQ_URL, region=s.AWS_REGION))
    
    cfg = ConnectorConfig(
        name="reddit",
        mode=mode,
        source="reddit",
        s3_bucket=s.S3_BUCKET,
        dsn=s.PG_DSN,
        sqs_queue_url=s.SQS_QUEUE_URL,
    )
    
    subreddit_list = [s.strip() for s in subreddits.split(",")]
    c = RedditConnector(cfg, s3, bus, subreddits=subreddit_list)
    
    typer.echo(f"Starting Reddit connector (mode={mode}, interval={interval}s, subreddits={subreddit_list})")
    
    while True:
        try:
            stats = c.run_once()
            typer.echo(f"[{datetime.now(timezone.utc).isoformat()}] {json.dumps(stats)}")
            time.sleep(interval)
        except KeyboardInterrupt:
            typer.echo("\nShutting down Reddit connector")
            break
        except Exception as e:
            typer.echo(f"Error during connector run: {e}", err=True)
            time.sleep(interval)


if __name__ == "__main__":
    app()
