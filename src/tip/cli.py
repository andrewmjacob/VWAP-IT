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


@app.command()
def run_edgar(
    mode: str = typer.Option("shadow", help="shadow or emit"),
    interval: int = typer.Option(180, help="Seconds between polling cycles"),
    ciks: str = typer.Option(None, help="Comma-separated CIKs to poll (e.g., '320193,789019')"),
    watchlist: str = typer.Option(None, help="Path to JSON file with CIK list"),
    max_rps: float = typer.Option(2.0, help="Max requests per second (capped at 8)"),
    forms: str = typer.Option(None, help="Comma-separated form types to track (default: 8-K,10-Q,10-K,etc)"),
    user_agent_name: str = typer.Option("TradingIntelPlatform", help="Name for SEC User-Agent header"),
    user_agent_email: str = typer.Option("contact@example.com", help="Email for SEC User-Agent header"),
    state_db: str = typer.Option("./edgar_state.db", help="Path to SQLite state database"),
):
    """Run the SEC EDGAR connector in a continuous loop.
    
    Polls data.sec.gov for new filings on a watchlist of CIKs.
    Respects SEC rate limits (≤10 rps, we default to 2).
    
    Examples:
        tip run-edgar --ciks "320193,789019"  # Apple and Microsoft
        tip run-edgar --watchlist ./ciks.json --interval 300
    """
    from tip.connectors.edgar import EDGARConnector, EDGARConfig, normalize_cik, DEFAULT_FORMS_ALLOWLIST
    
    # Load CIK list
    cik_list = []
    if ciks:
        cik_list = [normalize_cik(c.strip()) for c in ciks.split(",") if c.strip()]
    elif watchlist:
        import json as json_module
        from pathlib import Path
        wl_path = Path(watchlist)
        if not wl_path.exists():
            typer.echo(f"Error: Watchlist file not found: {watchlist}", err=True)
            raise typer.Exit(1)
        data = json_module.loads(wl_path.read_text())
        if isinstance(data, list):
            cik_list = [normalize_cik(c) for c in data]
        elif isinstance(data, dict) and "ciks" in data:
            cik_list = [normalize_cik(c) for c in data["ciks"]]
        else:
            typer.echo("Error: Watchlist must be a JSON array or object with 'ciks' key", err=True)
            raise typer.Exit(1)
    
    if not cik_list:
        typer.echo("Error: No CIKs provided. Use --ciks or --watchlist", err=True)
        raise typer.Exit(1)
    
    # Parse forms allowlist
    forms_list = DEFAULT_FORMS_ALLOWLIST.copy()
    if forms:
        forms_list = [f.strip() for f in forms.split(",") if f.strip()]
    
    s = Settings()
    s3 = S3Client(S3Config(bucket=s.S3_BUCKET, region=s.AWS_REGION))
    bus = None
    if mode == "emit" and s.SQS_QUEUE_URL:
        bus = SQSBus(SQSConfig(queue_url=s.SQS_QUEUE_URL, dlq_url=s.SQS_DLQ_URL, region=s.AWS_REGION))
    
    cfg = ConnectorConfig(
        name="edgar",
        mode=mode,
        source="edgar",
        s3_bucket=s.S3_BUCKET,
        dsn=s.PG_DSN,
        sqs_queue_url=s.SQS_QUEUE_URL,
    )
    
    edgar_cfg = EDGARConfig(
        ciks=cik_list,
        user_agent_name=user_agent_name,
        user_agent_email=user_agent_email,
        max_rps=max_rps,
        forms_allowlist=forms_list,
        state_db_path=state_db,
    )
    
    c = EDGARConnector(cfg, s3, bus, edgar_cfg=edgar_cfg)
    
    typer.echo(f"Starting EDGAR connector:")
    typer.echo(f"  Mode: {mode}")
    typer.echo(f"  Interval: {interval}s")
    typer.echo(f"  CIKs: {len(cik_list)} companies")
    typer.echo(f"  Max RPS: {edgar_cfg.max_rps}")
    typer.echo(f"  Forms: {', '.join(forms_list[:5])}{'...' if len(forms_list) > 5 else ''}")
    typer.echo(f"  User-Agent: {edgar_cfg.user_agent}")
    
    while True:
        try:
            stats = c.run_once()
            typer.echo(f"[{datetime.now(timezone.utc).isoformat()}] {json.dumps(stats)}")
            time.sleep(interval)
        except KeyboardInterrupt:
            typer.echo("\nShutting down EDGAR connector")
            break
        except Exception as e:
            typer.echo(f"Error during connector run: {e}", err=True)
            time.sleep(interval)


@app.command()
def lookup_cik(
    query: str = typer.Argument(..., help="Company name or ticker to search"),
):
    """Look up CIK for a company using SEC's company tickers API.
    
    Example:
        tip lookup-cik AAPL
        tip lookup-cik "Apple Inc"
    """
    import requests
    
    typer.echo(f"Searching SEC for: {query}")
    
    try:
        response = requests.get(
            "https://www.sec.gov/files/company_tickers.json",
            headers={"User-Agent": "TradingIntelPlatform contact@example.com (cik-lookup)"},
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        
        query_upper = query.upper()
        matches = []
        
        for entry in data.values():
            ticker = entry.get("ticker", "").upper()
            title = entry.get("title", "").upper()
            cik = entry.get("cik_str", "")
            
            if query_upper == ticker or query_upper in title:
                matches.append({
                    "cik": f"{int(cik):010d}",
                    "ticker": entry.get("ticker"),
                    "name": entry.get("title"),
                })
        
        if not matches:
            typer.echo("No matches found.")
            return
        
        typer.echo(f"\nFound {len(matches)} match(es):\n")
        for m in matches[:20]:
            typer.echo(f"  CIK: {m['cik']}  Ticker: {m['ticker']:<6}  Name: {m['name']}")
        
        if len(matches) > 20:
            typer.echo(f"\n  ... and {len(matches) - 20} more")
            
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
