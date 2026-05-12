"""Integration tests: database role privilege boundaries — D-095, D-067.

Requires TEST_DB_URL env var pointing to a real PostgreSQL instance with
the init scripts applied.  Skipped automatically when env var is absent
(local unit-test runs).

Tests:
  - clive_app cannot INSERT into audit log
  - clive_audit_writer cannot SELECT from clive_search.chunks
"""

from __future__ import annotations

import os

import asyncpg
import pytest

TEST_DB_URL = os.environ.get("TEST_DB_URL")


@pytest.fixture
async def superuser_conn():
    if not TEST_DB_URL:
        pytest.skip("TEST_DB_URL not set — skipping DB integration tests")
    conn = await asyncpg.connect(TEST_DB_URL)
    yield conn
    await conn.close()


@pytest.mark.asyncio
async def test_clive_app_cannot_insert_audit_log(superuser_conn):
    """clive_app role must not be able to write to the audit log (D-067)."""
    await superuser_conn.execute("SET ROLE clive_app")
    try:
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await superuser_conn.execute(
                """
                INSERT INTO clive_audit.event_log
                  (event_id, event_type, source_block, timestamp,
                   payload_hash, alignment_result, routing_outcome, zone_scope)
                VALUES
                  (gen_random_uuid(), 'test', 13, now(),
                   'hash', 'pass', 'test', 'personal')
                """
            )
    finally:
        await superuser_conn.execute("RESET ROLE")


@pytest.mark.asyncio
async def test_clive_audit_writer_cannot_read_chunks(superuser_conn):
    """clive_audit_writer role must not be able to read clive_search.chunks."""
    await superuser_conn.execute("SET ROLE clive_audit_writer")
    try:
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await superuser_conn.execute("SELECT count(*) FROM clive_search.chunks")
    finally:
        await superuser_conn.execute("RESET ROLE")


@pytest.mark.asyncio
async def test_clive_audit_writer_can_insert_event_log(superuser_conn):
    """clive_audit_writer role must be able to INSERT into the audit log (D-067)."""
    await superuser_conn.execute("SET ROLE clive_audit_writer")
    try:
        await superuser_conn.execute(
            """
            INSERT INTO clive_audit.event_log
              (event_id, event_type, source_block, timestamp,
               payload_hash, alignment_result, routing_outcome, zone_scope)
            VALUES
              (gen_random_uuid(), 'test.role_check', 13, now(),
               'testhash', 'pass', 'test', 'personal')
            """
        )
    finally:
        await superuser_conn.execute("RESET ROLE")
