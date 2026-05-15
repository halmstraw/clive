"""Prometheus metrics for Block 23 — Telegram surface (D-122).

Phase 2 application observability. All metrics are module-level singletons
created at import time. No side-effects at import beyond metric registration.
"""

from prometheus_client import Counter

# Total Telegram commands/messages handled, labelled by command type.
# Labels: query | ingest | delete | list | status | feedback | other
telegram_commands_total = Counter(
    "clive_telegram_commands_total",
    "Total number of Telegram commands and messages handled by Block 23",
    ["command"],
)
