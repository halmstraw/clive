"""Prometheus metrics for Block 8 — Query service (D-122).

Phase 2 application observability. All metrics are module-level singletons
created at import time. No side-effects at import beyond metric registration.
"""

from prometheus_client import Counter, Histogram

# Total query.received events handled.
queries_total = Counter(
    "clive_queries_total",
    "Total number of query.received events handled by Block 8",
)

# End-to-end query latency from event receipt to query.response emit.
query_duration_seconds = Histogram(
    "clive_query_duration_seconds",
    "End-to-end query handling duration in seconds (Block 8)",
    buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)

# Total retrieval chunks returned across all queries.
retrieval_chunks_returned_total = Counter(
    "clive_retrieval_chunks_returned_total",
    "Total number of retrieval chunks returned across all Block 8 queries",
)
