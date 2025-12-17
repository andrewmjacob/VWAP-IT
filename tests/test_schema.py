from __future__ import annotations

from tip.models import EventV1, EventType, Source
from datetime import datetime, timezone
import uuid


def test_event_model_roundtrip():
    ev = EventV1(
        eventId=str(uuid.uuid4()),
        schemaVersion="v1",
        eventType=EventType.SOCIAL_MENTIONS,
        source=Source.WSB,
        symbol="OPEN",
        entityId=None,
        tsEvent=datetime.now(timezone.utc),
        tsIngested=datetime.now(timezone.utc),
        dedupeKey="abc",
        severity=50,
        confidence=0.5,
        payload={"k": "v"},
    )
    dumped = ev.model_dump(mode="json")
    assert dumped["schemaVersion"] == "v1"
