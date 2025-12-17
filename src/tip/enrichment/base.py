from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Any, Optional
import hashlib
import uuid

from tip.models import EventV1, EventType, Source, PayloadRefs
from tip.storage.s3 import S3Client
from tip.db.session import get_session_sync
from tip.db.models import Event, EventArtifact, Outbox


@dataclass
class EnrichmentConfig:
    name: str
    mode: str  # shadow or emit
    dsn: str
    s3_bucket: str
    model_name: str
    per_day_usd_cap: float = 5.0
    per_event_token_limit: int = 2000


class BaseEnrichment:
    def __init__(self, cfg: EnrichmentConfig, s3: S3Client):
        self.cfg = cfg
        self.s3 = s3
        self.session_scope = get_session_sync(cfg.dsn)
        self._content_cache: set[str] = set()

    def annotate(self, event: EventV1) -> Dict[str, Any]:
        raise NotImplementedError

    def should_skip_cost(self, content_hash: str) -> bool:
        return content_hash in self._content_cache

    def run_on_event(self, event: EventV1) -> Optional[EventV1]:
        content = event.payload
        content_hash = hashlib.sha256(json_dumps_stable(content).encode("utf-8")).hexdigest()
        if self.should_skip_cost(content_hash):
            return None

        insight = self.annotate(event)
        self._content_cache.add(content_hash)

        now = datetime.now(timezone.utc)
        event_id = str(uuid.uuid4())
        insight_event = EventV1(
            eventId=event_id,
            schemaVersion="v1",
            eventType=EventType.MODEL_INSIGHT,
            source=Source.LLM,
            symbol=event.symbol,
            entityId=event.entityId,
            tsEvent=now,
            tsIngested=now,
            dedupeKey=f"insight:{event.eventId}:{self.cfg.model_name}:{content_hash[:12]}",
            severity=event.severity,
            confidence=insight.get("confidence"),
            payload=insight,
            payloadRefs=PayloadRefs(),
        )

        with self.session_scope() as session:
            session.add(
                EventArtifact(
                    event_id=event.eventId,
                    artifact_type="MODEL.SUMMARY",
                    model_name=self.cfg.model_name,
                    artifact_json=insight,
                    artifact_s3_uri=None,
                    created_at=now,
                )
            )
            session.add(
                Event(
                    event_id=insight_event.eventId,
                    schema_version=insight_event.schemaVersion,
                    event_type=insight_event.eventType.value,
                    source=insight_event.source.value,
                    symbol=insight_event.symbol,
                    entity_id=insight_event.entityId,
                    ts_event=insight_event.tsEvent,
                    ts_ingested=insight_event.tsIngested,
                    dedupe_key=insight_event.dedupeKey,
                    severity=insight_event.severity,
                    confidence=insight_event.confidence,
                    payload_json=insight_event.payload,
                    raw_s3_uri=None,
                    normalized_s3_uri=None,
                    hash=None,
                    created_at=now,
                )
            )
            if self.cfg.mode == "emit":
                session.add(Outbox(event_id=insight_event.eventId, payload=insight_event.model_dump(mode="json")))

        self.s3.write_event(insight_event.eventType.value, now, insight_event.eventId, insight_event.model_dump(mode="json"))
        return insight_event


def json_dumps_stable(obj: Dict[str, Any]) -> str:
    import json

    return json.dumps(obj, sort_keys=True, separators=(",", ":"))
