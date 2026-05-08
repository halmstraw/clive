"""Tests for retrieval broker (unit-level — no DB required)."""

from __future__ import annotations

import pytest

import orchestrator.retrieval as retrieval_module


@pytest.mark.asyncio
async def test_retrieve_raises_when_pool_not_initialised():
    retrieval_module._pool = None
    with pytest.raises(RuntimeError, match="not initialised"):
        await retrieval_module.retrieve(
            retrieval_query="test",
            zone_scope="personal",
            result_limit=5,
            conversation_id=None,
        )


@pytest.mark.asyncio
async def test_retrieve_system_document_raises_when_pool_not_initialised():
    retrieval_module._pool = None
    with pytest.raises(RuntimeError, match="not initialised"):
        await retrieval_module.retrieve_system_document(
            document_type="personality",
            zone_scope="personal",
        )
