from __future__ import annotations

from datetime import datetime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import String, DateTime, Integer, BigInteger, JSON, ForeignKey, UniqueConstraint, Index
import uuid


class Base(DeclarativeBase):
    pass


class Event(Base):
    __tablename__ = "events"
    event_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    schema_version: Mapped[str] = mapped_column(String(10), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    symbol: Mapped[str | None] = mapped_column(String(16))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    ts_event: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ts_ingested: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    dedupe_key: Mapped[str] = mapped_column(String(255), unique=True)
    severity: Mapped[int] = mapped_column(Integer)
    confidence: Mapped[float | None]
    payload_json: Mapped[dict] = mapped_column(JSON)
    raw_s3_uri: Mapped[str | None] = mapped_column(String(512))
    normalized_s3_uri: Mapped[str | None] = mapped_column(String(512))
    hash: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    artifacts = relationship("EventArtifact", back_populates="event")

    __table_args__ = (
        Index("ix_events_symbol", "symbol"),
    )


class EventArtifact(Base):
    __tablename__ = "event_artifacts"
    artifact_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.event_id"))
    artifact_type: Mapped[str] = mapped_column(String(64))
    model_name: Mapped[str | None] = mapped_column(String(64))
    artifact_json: Mapped[dict] = mapped_column(JSON)
    artifact_s3_uri: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    event = relationship("Event", back_populates="artifacts")


class Outbox(Base):
    __tablename__ = "outbox"
    outbox_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_id: Mapped[uuid.UUID]
    payload: Mapped[dict] = mapped_column(JSON)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CanaryRun(Base):
    __tablename__ = "canary_runs"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    service: Mapped[str] = mapped_column(String(64))
    version: Mapped[str] = mapped_column(String(32))
    stats_json: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
