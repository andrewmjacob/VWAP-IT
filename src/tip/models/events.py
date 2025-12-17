from __future__ import annotations

from enum import Enum
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, UUID4, field_validator
from datetime import datetime, timezone


class EventType(str, Enum):
    DISCLOSURE_FILING = "DISCLOSURE.FILING"
    SOCIAL_MENTIONS = "SOCIAL.MENTIONS"
    MARKET_BAR = "MARKET.BAR"
    MODEL_INSIGHT = "MODEL.INSIGHT"
    SYSTEM_HEALTH = "SYSTEM.HEALTH"


class Source(str, Enum):
    EDGAR = "edgar"
    WSB = "wsb"
    MARKET = "market"
    LLM = "llm"
    SYSTEM = "system"


class PayloadRefs(BaseModel):
    raw: Optional[str] = None
    normalized: Optional[str] = None
    enriched: Optional[str] = None


class EventV1(BaseModel):
    eventId: UUID4 = Field(..., description="UUID for the event")
    schemaVersion: str = Field("v1")
    eventType: EventType
    source: Source
    symbol: Optional[str] = Field(default=None, pattern=r"^[A-Z.\-]{1,16}$")
    entityId: Optional[str] = None
    tsEvent: datetime
    tsIngested: datetime
    dedupeKey: str
    severity: int = Field(ge=0, le=100)
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    payload: Dict[str, Any] = Field(default_factory=dict)
    payloadRefs: PayloadRefs = Field(default_factory=PayloadRefs)

    @field_validator("tsEvent", "tsIngested")
    @classmethod
    def ensure_timezone_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("Timestamp must be timezone-aware (UTC)")
        return v.astimezone(timezone.utc)

    model_config = {
        "extra": "forbid",
    }
