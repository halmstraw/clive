"""PostgreSQL connection pool for Block 8 — LLM usage tracking (D-125, v0.6).

Block 8 writes directly to clive_state.llm_usage for spend tracking.
This follows the same pattern as Block 23's db.py for feedback writes.
All other Block 8 → storage interactions route through Block 13 (D-003).
"""

from __future__ import annotations

import os

import asyncpg
import structlog

log = structlog.get_logger()

_pool: asyncpg.Pool | None = None


async def init_pool() -> None:
    """Initialise the Block 8 DB pool (clive_app role)."""
    global _pool
    dsn = (
        f"postgresql://clive_app:{os.environ['APP_DB_PASSWORD']}"
        f"@{os.environ.get('POSTGRES_HOST', 'postgres')}:5432/clive"
    )
    _pool = await asyncpg.create_pool(dsn, min_size=1, max_size=3)
    log.info("query_db_pool_initialised")


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("DB pool not initialised")
    return _pool
