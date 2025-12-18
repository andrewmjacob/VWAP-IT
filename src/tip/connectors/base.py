from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Dict, Any, Optional
import hashlib
import uuid

from tip.models import EventV1, EventType, Source, PayloadRefs
from tip.storage.s3 import S3Client
from tip.db.session import get_session_sync
from tip.db.models import Event, Outbox
from tip.bus.sqs import SQSBus

logger = logging.getLogger(__name__)


@dataclass
class ConnectorConfig:
    name: str
    mode: str  # "shadow" or "emit"
    source: str  # e.g., "wsb", "reddit", etc.
    s3_bucket: str
    dsn: str
    sqs_queue_url: Optional[str] = None


class BaseConnector:
    def __init__(self, cfg: ConnectorConfig, s3: S3Client, bus: Optional[SQSBus] = None):
        self.cfg = cfg
        self.s3 = s3
        self.bus = bus
        self.session_scope = get_session_sync(cfg.dsn)

    def fetch(self) -> Iterable[Dict[str, Any]]:
        raise NotImplementedError

    def normalize(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError

    def run_once(self) -> Dict[str, Any]:
        stats = {"fetched": 0, "ingested": 0, "deduped": 0, "errors": 0}
        now = datetime.now(timezone.utc)
        for raw in self.fetch():
            stats["fetched"] += 1
            try:
                normalized = self.normalize(raw)
                event_id = str(uuid.uuid4())
                ts_event = normalized.get("tsEvent", now)
                # Write raw to S3
                raw_uri = self.s3.write_raw(self.cfg.source, ts_event, event_id, raw)

                # Build event
                dedupe_key = normalized.get("dedupeKey") or hashlib.sha256(
                    json_dumps_stable(normalized).encode("utf-8")
                ).hexdigest()
                event = EventV1(
                    eventId=event_id,
                    schemaVersion="v1",
                    eventType=normalized["eventType"],
                    source=self.cfg.source,
                    symbol=normalized.get("symbol"),
                    entityId=normalized.get("entityId"),
                    tsEvent=ts_event,
                    tsIngested=now,
                    dedupeKey=dedupe_key,
                    severity=normalized.get("severity", 50),
                    confidence=normalized.get("confidence"),
                    payload=normalized.get("payload", {}),
                    payloadRefs=PayloadRefs(raw=raw_uri),
                )

                with self.session_scope() as session:
                    # Insert event row if not exists by dedupe_key
                    exists = session.query(Event).filter_by(dedupe_key=event.dedupeKey).one_or_none()
                    if exists:
                        stats["deduped"] += 1
                        continue

                    # Persist event row
                    ev_row = Event(
                        event_id=event.eventId,
                        schema_version=event.schemaVersion,
                        event_type=event.eventType.value,
                        source=event.source.value,
                        symbol=event.symbol,
                        entity_id=event.entityId,
                        ts_event=event.tsEvent,
                        ts_ingested=event.tsIngested,
                        dedupe_key=event.dedupeKey,
                        severity=event.severity,
                        confidence=event.confidence,
                        payload_json=event.payload,
                        raw_s3_uri=event.payloadRefs.raw,
                        normalized_s3_uri=None,
                        hash=None,
                        created_at=now,
                    )
                    session.add(ev_row)

                    if self.cfg.mode == "emit" and self.bus:
                        session.add(Outbox(event_id=event.eventId, payload=event.model_dump(mode="json")))

                stats["ingested"] += 1
                # Write canonical event to S3 after commit for lineage
                self.s3.write_event(event.eventType.value, ts_event, event_id, event.model_dump(mode="json"))

                # Publish only via an outbox dispatcher elsewhere
            except Exception:
                logger.exception("Error processing event")
                stats["errors"] += 1
        return stats


def json_dumps_stable(obj: Dict[str, Any]) -> str:
    import json

    return json.dumps(obj, sort_keys=True, separators=(",", ":"))
