-- Schema initialization for Trading Intelligence Platform
CREATE TABLE IF NOT EXISTS events (
  event_id UUID PRIMARY KEY,
  schema_version VARCHAR(10) NOT NULL,
  event_type VARCHAR(64) NOT NULL,
  source VARCHAR(32) NOT NULL,
  symbol VARCHAR(16),
  entity_id VARCHAR(64),
  ts_event TIMESTAMPTZ NOT NULL,
  ts_ingested TIMESTAMPTZ NOT NULL,
  dedupe_key VARCHAR(255) UNIQUE NOT NULL,
  severity INT NOT NULL,
  confidence DOUBLE PRECISION,
  payload_json JSONB NOT NULL,
  raw_s3_uri VARCHAR(512),
  normalized_s3_uri VARCHAR(512),
  hash VARCHAR(64),
  created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_events_event_type ON events(event_type);
CREATE INDEX IF NOT EXISTS ix_events_symbol ON events(symbol);
CREATE INDEX IF NOT EXISTS ix_events_ts_event ON events(ts_event);

CREATE TABLE IF NOT EXISTS event_artifacts (
  artifact_id BIGSERIAL PRIMARY KEY,
  event_id UUID REFERENCES events(event_id),
  artifact_type VARCHAR(64) NOT NULL,
  model_name VARCHAR(64),
  artifact_json JSONB NOT NULL,
  artifact_s3_uri VARCHAR(512),
  created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS outbox (
  outbox_id BIGSERIAL PRIMARY KEY,
  event_id UUID NOT NULL,
  payload JSONB NOT NULL,
  published_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS canary_runs (
  id BIGSERIAL PRIMARY KEY,
  service VARCHAR(64) NOT NULL,
  version VARCHAR(32) NOT NULL,
  stats_json JSONB NOT NULL,
  status VARCHAR(16) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL
);
