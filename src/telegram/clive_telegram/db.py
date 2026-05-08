"""PostgreSQL connection pool for Block 23 administrative operations.

Used exclusively by the D-079 system document activation flow.
All other Block 23 → data interactions route through Block 13 (D-003).
"""

from __future__ import annotations

import os

import asyncpg
import structlog

log = structlog.get_logger()

_pool: asyncpg.Pool | None = None


async def init_pool() -> None:
    global _pool
    dsn = (
        f"postgresql://clive_app:{os.environ['APP_DB_PASSWORD']}"
        f"@{os.environ.get('POSTGRES_HOST', 'postgres')}:5432/clive"
    )
    _pool = await asyncpg.create_pool(dsn, min_size=1, max_size=3)
    log.info("telegram_db_pool_initialised")


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("DB pool not initialised")
    return _pool
