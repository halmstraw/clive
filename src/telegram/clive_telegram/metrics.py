"""Prometheus metrics for Block 23 — Telegram surface (D-122, D-125).

Phase 2 application observability (D-122). Block 20 rate limit metric (D-125).
All metrics are module-level singletons created at import time.
No side-effects at import beyond metric registration.
"""

from prometheus_client import Counter

# Total Telegram commands/messages handled, labelled by command type.
# Labels: query | ingest | delete | list | status | feedback | other
telegram_commands_total = Counter(
    "clive_telegram_commands_total",
    "Total number of Telegram commands and messages handled by Block 23",
    ["command"],
)

# Block 20 — queries rejected by the inbound rate limiter (D-125).
# Incremented when RATE_LIMIT_QUERIES_PER_HOUR is set and the limit is reached.
rate_limited_total = Counter(
    "clive_rate_limited_total",
    "Total number of inbound queries rejected by Block 23 rate limiter",
)
