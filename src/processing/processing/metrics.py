"""Prometheus metrics for Block 15 — Processing service (D-122).

Phase 2 application observability. All metrics are module-level singletons
created at import time. No side-effects at import beyond metric registration.
"""

from prometheus_client import Counter, Histogram

# Total ingest events handled, by final status (processed | rejected).
ingest_total = Counter(
    "clive_ingest_total",
    "Total number of ingest events handled by Block 15",
    ["status"],  # "processed" or "rejected"
)

# Total chunks written to Block 16 storage across all ingest events.
chunks_created_total = Counter(
    "clive_chunks_created_total",
    "Total number of chunks written to Block 16 storage by Block 15",
)

# End-to-end processing duration from event receipt to ingest.processed/rejected emit.
processing_duration_seconds = Histogram(
    "clive_processing_duration_seconds",
    "End-to-end ingest processing duration in seconds (Block 15)",
    buckets=(0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0),
)
