from __future__ import annotations

import json
from datetime import datetime, timezone
from sqlalchemy import select
from tip.db.session import get_session_sync
from tip.db.models import Outbox
from tip.bus.sqs import SQSBus


def dispatch_once(dsn: str, bus: SQSBus, batch_size: int = 100) -> int:
    dispatched = 0
    with get_session_sync(dsn)() as session:
        rows = (
            session.execute(
                select(Outbox).where(Outbox.published_at.is_(None)).order_by(Outbox.outbox_id).limit(batch_size)
            )
            .scalars()
            .all()
        )
        for row in rows:
            bus.publish(row.payload)
            row.published_at = datetime.now(timezone.utc)
            dispatched += 1
    return dispatched
