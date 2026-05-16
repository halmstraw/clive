"""Block 11 — Full cross-session memory (D-128, v0.7).

Three capabilities, all internal to Block 8 (D-003 compliant):

1. Semantic entity retrieval — pgvector cosine similarity search over
   clive_state.memory_entities returns the top-K most relevant facts about the
   owner before context assembly (AC-3).

2. Entity storage — after each response, extracted entities from llm.extract_entities
   are persisted here with 1536-dim embeddings (D-096, text-embedding-3-small).
   Called by handler.py post-response (AC-2).

3. Memory consolidation — compresses old turns into a summary row when
   turn count > 100 or oldest turn > 48h. Prunes raw turns after summarisation.
   Called by handler.py post-response (AC-5).

All DB access uses the clive_app pool from db.py.
All functions are non-fatal: exceptions are caught, logged, and the caller receives
a safe default ([] for retrieval, None for storage/consolidation).

Memory retrieval is internal to Block 8 — no new events required (D-003).
Direct DB access is consistent with the llm_usage write pattern established at v0.6.

asyncpg pgvector note: asyncpg has no built-in pgvector codec.
Embeddings (list[float]) must be converted to str() before passing as
a $N::vector SQL parameter — same pattern as processing/store.py.
str([1.0, 2.0, ...]) produces "[1.0, 2.0, ...]" which pgvector parses correctly.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Callable

import structlog

from .db import get_pool

log = structlog.get_logger()

# Consolidation thresholds — D-128
CONSOLIDATION_TURN_THRESHOLD = 100   # trigger when conversation has >100 turns
CONSOLIDATION_AGE_HOURS = 48         # trigger when oldest turn is >48h old
CONSOLIDATION_BATCH_SIZE = 50        # max turns to consolidate per pass


async def retrieve_entities(
    query_embedding: list[float],
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """Pgvector cosine similarity search over clive_state.memory_entities.

    Returns up to top_k results ordered by cosine similarity (closest first).
    Returns [] gracefully on empty table or any DB error.

    AC-3: called by handler.py before context assembly.

    Args:
        query_embedding: 1536-dim embedding of the current user query.
        top_k: maximum number of entities to return (default 5, per D-128).

    Returns:
        list of {entity_id, entity_type, key, value, similarity_score}
    """
    try:
        pool = get_pool()
        # asyncpg has no pgvector codec — convert list to str before passing
        embedding_str = str(query_embedding)
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT entity_id,
                       entity_type,
                       key,
                       value,
                       1 - (embedding <=> $1::vector) AS similarity_score
                FROM   clive_state.memory_entities
                WHERE  embedding IS NOT NULL
                ORDER  BY embedding <=> $1::vector
                LIMIT  $2
                """,
                embedding_str,
                top_k,
            )
        return [
            {
                "entity_id": str(row["entity_id"]),
                "entity_type": row["entity_type"],
                "key": row["key"],
                "value": row["value"],
                "similarity_score": float(row["similarity_score"]),
            }
            for row in rows
        ]
    except Exception as exc:
        log.error("memory_retrieve_failed", error=str(exc))
        return []


async def store_entities(
    entities: list[dict[str, Any]],
    source_turn_id: uuid.UUID | None,
    embeddings: list[list[float]],
) -> None:
    """Insert extracted entities with embeddings into clive_state.memory_entities.

    Non-fatal: logs and returns on DB error.

    AC-2: called by handler.py after each successful response.

    Args:
        entities:       list of {entity_type, key, value} (validated by llm.extract_entities)
        source_turn_id: nullable — FK reference to the conversation_turns row that
                        sourced these entities. May be None when the turn_id is not
                        available (common at v0.7 since turn writes are orchestrator-owned).
        embeddings:     parallel list of 1536-dim vectors, one per entity.
    """
    if not entities:
        return
    try:
        pool = get_pool()
        async with pool.acquire() as conn:
            for entity, embedding in zip(entities, embeddings):
                # asyncpg has no pgvector codec — convert list to str before passing
                embedding_str = str(embedding)
                await conn.execute(
                    """
                    INSERT INTO clive_state.memory_entities
                        (entity_type, key, value, source_turn_id, embedding)
                    VALUES ($1, $2, $3, $4, $5::vector)
                    """,
                    entity["entity_type"],
                    entity["key"],
                    entity["value"],
                    source_turn_id,
                    embedding_str,
                )
        log.info("memory_entities_stored", count=len(entities))
    except Exception as exc:
        log.error("memory_store_failed", error=str(exc))


async def consolidate_if_needed(
    conversation_id: uuid.UUID,
    llm_summarise: Callable,
) -> None:
    """Check consolidation threshold; compress old turns into a summary if triggered.

    Trigger conditions (either is sufficient):
      - turn count > CONSOLIDATION_TURN_THRESHOLD (100)
      - oldest turn > CONSOLIDATION_AGE_HOURS (48h) old

    On trigger:
      1. Fetch the oldest CONSOLIDATION_BATCH_SIZE (50) turns.
      2. Call llm_summarise(turn_text) → (summary_text, embedding).
         (dependency-injected for testability — pass llm.summarise_turns)
      3. Insert summary row into clive_state.conversation_summaries.
      4. DELETE the consolidated turns from clive_state.conversation_turns.

    Below threshold: returns immediately (no-op).
    Non-fatal: logs and returns on DB or LLM error.

    AC-5: called by handler.py post-response (after query.response emitted).

    Args:
        conversation_id: UUID of the conversation to check.
        llm_summarise:   async callable(turn_text: str) -> (summary_text, embedding).
                         Use llm.summarise_turns.
    """
    try:
        pool = get_pool()

        # Step 1: Check threshold (first connection — released before LLM call)
        async with pool.acquire() as conn:
            meta = await conn.fetchrow(
                """
                SELECT COUNT(*)       AS cnt,
                       MIN(created_at) AS oldest
                FROM   clive_state.conversation_turns
                WHERE  conversation_id = $1
                """,
                conversation_id,
            )

            if meta is None or int(meta["cnt"]) == 0:
                return

            turn_count = int(meta["cnt"])
            oldest_at: datetime = meta["oldest"]

            # Ensure timezone-aware comparison
            if oldest_at.tzinfo is None:
                oldest_at = oldest_at.replace(tzinfo=timezone.utc)

            age_hours = (datetime.now(timezone.utc) - oldest_at).total_seconds() / 3600

            count_triggered = turn_count > CONSOLIDATION_TURN_THRESHOLD
            age_triggered = age_hours > CONSOLIDATION_AGE_HOURS

            if not count_triggered and not age_triggered:
                return  # Below threshold — no-op

            log.info(
                "consolidation_triggered",
                conversation_id=str(conversation_id),
                turn_count=turn_count,
                age_hours=round(age_hours, 1),
                count_triggered=count_triggered,
                age_triggered=age_triggered,
            )

            # Fetch the oldest batch of turns to consolidate
            rows = await conn.fetch(
                """
                SELECT turn_id, turn_number, role, content
                FROM   clive_state.conversation_turns
                WHERE  conversation_id = $1
                ORDER  BY turn_number ASC
                LIMIT  $2
                """,
                conversation_id,
                CONSOLIDATION_BATCH_SIZE,
            )

            if not rows:
                return

        # Unpack outside the connection (released above)
        turn_ids = [r["turn_id"] for r in rows]
        turn_numbers = [r["turn_number"] for r in rows]
        turn_text = "\n".join(
            f"{r['role'].upper()}: {r['content']}" for r in rows
        )

        # Step 2: LLM summarisation (outside DB connection — don't hold conn during IO)
        summary_text, summary_embedding = await llm_summarise(turn_text)

        # Step 3: Persist summary and delete raw turns (second connection)
        # asyncpg has no pgvector codec — convert list to str before passing
        summary_embedding_str = str(summary_embedding)
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO clive_state.conversation_summaries
                    (conversation_id, summary_text,
                     turn_range_start, turn_range_end, turn_count, embedding)
                VALUES ($1, $2, $3, $4, $5, $6::vector)
                """,
                conversation_id,
                summary_text,
                min(turn_numbers),
                max(turn_numbers),
                len(rows),
                summary_embedding_str,
            )
            await conn.execute(
                "DELETE FROM clive_state.conversation_turns WHERE turn_id = ANY($1::uuid[])",
                turn_ids,
            )

        log.info(
            "consolidation_complete",
            conversation_id=str(conversation_id),
            turns_consolidated=len(rows),
            turn_range=f"{min(turn_numbers)}–{max(turn_numbers)}",
        )

    except Exception as exc:
        log.error("consolidation_failed", error=str(exc))
