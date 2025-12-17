from __future__ import annotations

from datetime import datetime, timezone
import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
from typing import List, Dict, Any
from io import BytesIO
from tip.storage.s3 import S3Client


def build_daily_parquet_index(s3: S3Client, event_type: str, events: List[Dict[str, Any]], ts: datetime) -> str:
    # Minimal columns for analytics
    rows = [
        {
            "event_id": e["eventId"],
            "event_type": e["eventType"],
            "source": e["source"],
            "symbol": e.get("symbol"),
            "ts_event": e["tsEvent"],
            "ts_ingested": e["tsIngested"],
            "severity": e.get("severity", 0),
        }
        for e in events
    ]
    table = pa.Table.from_pylist(rows)
    buf = BytesIO()
    pq.write_table(table, buf)
    key = s3.write_index_parquet_key(event_type, ts)
    # Direct put because we want parquet mime type; reuse client
    s3.s3.put_object(
        Bucket=s3.cfg.bucket,
        Key=key,
        Body=buf.getvalue(),
        ContentType="application/octet-stream",
    )
    return f"s3://{s3.cfg.bucket}/{key}"
