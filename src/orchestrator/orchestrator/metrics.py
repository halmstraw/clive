"""Prometheus metrics for Block 13 — Orchestrator (D-122).

Phase 2 application observability. All metrics are module-level singletons
created at import time. No side-effects at import beyond metric registration.
"""

from prometheus_client import Counter

# Total events published onto the bus, labelled by event type.
events_published_total = Counter(
    "clive_events_published_total",
    "Total number of events published to the Block 13 event bus",
    ["event_type"],
)

# Total audit log writes (successes — exceptions surface to caller).
audit_writes_total = Counter(
    "clive_audit_writes_total",
    "Total number of audit log writes performed by Block 13",
)
