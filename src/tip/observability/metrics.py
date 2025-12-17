from __future__ import annotations

from prometheus_client import Counter, Histogram

INGESTION_LAG = Histogram(
    "tip_ingestion_lag_seconds",
    "Ingestion lag in seconds",
    buckets=(0.1, 0.5, 1, 2, 5, 10, 30, 60, 120, 300),
)
ERRORS = Counter("tip_errors_total", "Errors per component", ["component"]) 
DEDUPES = Counter("tip_deduped_total", "Deduplicated events total")
ENRICH_LAT = Histogram("tip_enrichment_latency_seconds", "Enrichment latency seconds")
LLM_SPEND = Counter("tip_llm_spend_usd_total", "LLM spend in USD")
