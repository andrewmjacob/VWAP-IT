from __future__ import annotations

from datetime import datetime
from sqlalchemy import select
from tip.db.session import get_session_sync
from tip.db.models import Event
from tip.bus.sqs import SQSBus


def replay_by_ts_event(dsn: str, bus: SQSBus, start: datetime, end: datetime) -> int:
    cnt = 0
    with get_session_sync(dsn)() as session:
        for row in session.execute(select(Event).where(Event.ts_event.between(start, end)).order_by(Event.ts_event)):
            bus.publish(row[0].payload_json)
            cnt += 1
    return cnt


def replay_by_ts_ingested(dsn: str, bus: SQSBus, start: datetime, end: datetime) -> int:
    cnt = 0
    with get_session_sync(dsn)() as session:
        for row in session.execute(select(Event).where(Event.ts_ingested.between(start, end)).order_by(Event.ts_ingested)):
            bus.publish(row[0].payload_json)
            cnt += 1
    return cnt
