"""Prometheus metrics for Block 8 — Query service (D-122, D-125).

Phase 2 application observability (D-122). Block 20 cost metrics (D-125).
All metrics are module-level singletons created at import time.
No side-effects at import beyond metric registration.
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

# Block 20 — LLM token usage by model and token type (D-125).
# Labels: model (e.g. "anthropic/claude-sonnet-4-20250514"), type (prompt | completion)
llm_tokens_total = Counter(
    "clive_llm_tokens_total",
    "Total LLM tokens used by Block 8, labelled by model and token type",
    ["model", "type"],
)

# Block 20 — LLM cumulative cost by model (D-125).
# Label: model (e.g. "anthropic/claude-sonnet-4-20250514")
llm_cost_usd_total = Counter(
    "clive_llm_cost_usd_total",
    "Cumulative LLM cost in USD tracked by Block 8, labelled by model",
    ["model"],
)

# Block 20 — number of times the daily spend cap gate fired (D-125).
llm_cost_cap_exceeded_total = Counter(
    "clive_llm_cost_cap_exceeded_total",
    "Number of times the daily LLM spend cap was reached (Block 8)",
)
