from __future__ import annotations

from typing import Iterable, Dict, Any
from datetime import datetime, timezone

from tip.connectors.base import BaseConnector, ConnectorConfig
from tip.models import EventType, Source


class WSBMockConnector(BaseConnector):
    def fetch(self) -> Iterable[Dict[str, Any]]:
        # In real impl, read from API or file. Here yield a simple post.
        yield {
            "post_id": "abc123",
            "symbol": "OPEN",
            "text": "OPEN to the moon",
            "ts": datetime.now(timezone.utc).isoformat(),
            "upvotes": 420,
        }

    def normalize(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "eventType": EventType.SOCIAL_MENTIONS,
            "symbol": raw.get("symbol"),
            "entityId": None,
            "tsEvent": datetime.fromisoformat(raw["ts"]),
            "severity": min(100, int(raw.get("upvotes", 0) // 10)),
            "payload": {
                "postId": raw["post_id"],
                "text": raw.get("text"),
                "upvotes": raw.get("upvotes", 0),
            },
            "dedupeKey": f"wsb:{raw['post_id']}",
        }
