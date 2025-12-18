from __future__ import annotations

import logging
from typing import Any, Dict

from tip.consumers.base import BaseConsumer, ConsumerConfig
from tip.db.session import get_session_sync
from tip.db.models import EventArtifact

logger = logging.getLogger(__name__)


class EventProcessor(BaseConsumer):
    """
    Processes events from SQS and creates artifacts.
    
    This is a simple example consumer that:
    1. Receives events from SQS
    2. Extracts ticker mentions from the payload
    3. Stores processed artifacts in the database
    """

    def __init__(self, config: ConsumerConfig, dsn: str):
        super().__init__(config)
        self.session_scope = get_session_sync(dsn)

    def process_event(self, event: Dict[str, Any]) -> bool:
        """Process a single event."""
        event_id = event.get("eventId")
        event_type = event.get("eventType")
        payload = event.get("payload", {})

        logger.info(f"Processing event {event_id} ({event_type})")

        # Extract insights based on event type
        if event_type == "SOCIAL.MENTIONS":
            return self._process_social_mentions(event_id, payload)
        else:
            # Log and acknowledge other event types
            logger.debug(f"No processor for event type: {event_type}")
            return True

    def _process_social_mentions(self, event_id: str, payload: Dict[str, Any]) -> bool:
        """Process social mention events - extract ticker sentiment."""
        tickers = payload.get("tickers", [])
        sentiment = payload.get("sentiment")
        
        if not tickers:
            return True  # Nothing to process

        # Store artifact for each ticker mention
        from datetime import datetime, timezone
        
        with self.session_scope() as session:
            for ticker in tickers:
                artifact = EventArtifact(
                    event_id=event_id,
                    artifact_type="ticker_mention",
                    model_name="event_processor_v1",
                    artifact_json={
                        "ticker": ticker,
                        "sentiment": sentiment,
                        "source_event_type": "SOCIAL.MENTIONS",
                    },
                    artifact_s3_uri=None,
                    created_at=datetime.now(timezone.utc),
                )
                session.add(artifact)
            
            logger.info(f"Created {len(tickers)} ticker artifacts for event {event_id}")

        return True

