from __future__ import annotations

import gzip
import io
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional
import os
import boto3


@dataclass
class S3Config:
    bucket: str
    region: str = "us-east-1"
    endpoint_url: Optional[str] = None


class S3Client:
    def __init__(self, cfg: S3Config):
        self.cfg = cfg
        endpoint = cfg.endpoint_url or os.getenv("AWS_ENDPOINT_URL")
        self.s3 = boto3.client("s3", region_name=cfg.region, endpoint_url=endpoint)

    def _put_gzip_json(self, key: str, obj: Dict[str, Any]) -> str:
        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode="wb") as gz:
            gz.write(json.dumps(obj, separators=(",", ":")).encode("utf-8"))
        buf.seek(0)
        self.s3.put_object(
            Bucket=self.cfg.bucket,
            Key=key,
            Body=buf.read(),
            ContentType="application/json",
            ContentEncoding="gzip",
        )
        return f"s3://{self.cfg.bucket}/{key}"

    @staticmethod
    def _ymd(ts: datetime) -> Dict[str, str]:
        ts = ts.astimezone(timezone.utc)
        return {"yyyy": f"{ts.year:04d}", "mm": f"{ts.month:02d}", "dd": f"{ts.day:02d}"}

    def write_raw(self, source: str, ts_event: datetime, event_id: str, payload: Dict[str, Any]) -> str:
        ymd = self._ymd(ts_event)
        key = f"raw/{source}/yyyy={ymd['yyyy']}/mm={ymd['mm']}/dd={ymd['dd']}/{event_id}.json.gz"
        return self._put_gzip_json(key, payload)

    def write_event(self, event_type: str, ts_event: datetime, event_id: str, event_obj: Dict[str, Any]) -> str:
        ymd = self._ymd(ts_event)
        key = (
            f"events/eventType={event_type}/yyyy={ymd['yyyy']}/mm={ymd['mm']}/dd={ymd['dd']}/{event_id}.json.gz"
        )
        return self._put_gzip_json(key, event_obj)

    def write_enriched(
        self, model_name: str, event_type: str, ts_event: datetime, event_id: str, payload: Dict[str, Any]
    ) -> str:
        ymd = self._ymd(ts_event)
        key = (
            f"enriched/model={model_name}/eventType={event_type}/yyyy={ymd['yyyy']}/mm={ymd['mm']}/dd={ymd['dd']}/{event_id}.json.gz"
        )
        return self._put_gzip_json(key, payload)

    def write_index_parquet_key(self, event_type: str, ts: datetime) -> str:
        ymd = self._ymd(ts)
        return f"indexes/daily/eventType={event_type}/yyyy={ymd['yyyy']}/mm={ymd['mm']}/dd={ymd['dd']}/part-000.parquet"
