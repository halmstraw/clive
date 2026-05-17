"""Tests for orchestrator retrieval.py — direct DB-layer function tests."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

import orchestrator.retrieval as retrieval_module


def _make_mock_pool(conn: AsyncMock) -> MagicMock:
    """Build a minimal mock asyncpg pool with an async context manager on acquire()."""
    mock_pool = MagicMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=None)
    mock_pool.acquire = MagicMock(return_value=ctx)
    return mock_pool


def _set_pool(pool) -> None:
    retrieval_module._pool = pool


def _get_original_pool():
    return retrieval_module._pool


# ---------------------------------------------------------------------------
# _is_valid_zone
# ---------------------------------------------------------------------------

class TestIsValidZone:
    @pytest.mark.asyncio
    async def test_returns_true_when_pool_none(self):
        original = _get_original_pool()
        try:
            _set_pool(None)
            result = await retrieval_module._is_valid_zone("personal")
            assert result is True
        finally:
            _set_pool(original)

    @pytest.mark.asyncio
    async def test_returns_true_for_known_zone(self):
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value={"1": 1})

        original = _get_original_pool()
        try:
            _set_pool(_make_mock_pool(mock_conn))
            result = await retrieval_module._is_valid_zone("personal")
            assert result is True
        finally:
            _set_pool(original)

    @pytest.mark.asyncio
    async def test_returns_false_for_unknown_zone(self):
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value=None)

        original = _get_original_pool()
        try:
            _set_pool(_make_mock_pool(mock_conn))
            result = await retrieval_module._is_valid_zone("unknown_zone")
            assert result is False
        finally:
            _set_pool(original)

    @pytest.mark.asyncio
    async def test_fails_open_on_db_error(self):
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(side_effect=Exception("db error"))

        original = _get_original_pool()
        try:
            _set_pool(_make_mock_pool(mock_conn))
            result = await retrieval_module._is_valid_zone("personal")
            assert result is True  # fail open
        finally:
            _set_pool(original)


# ---------------------------------------------------------------------------
# retrieve_system_document
# ---------------------------------------------------------------------------

class TestRetrieveSystemDocument:
    @pytest.mark.asyncio
    async def test_returns_active_document(self):
        mock_row = {
            "document_content": "You are CLIVE.",
            "version_id": uuid.uuid4(),
            "created_at": datetime.now(timezone.utc),
            "is_active": True,
        }
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value=mock_row)

        original = _get_original_pool()
        try:
            _set_pool(_make_mock_pool(mock_conn))
            result = await retrieval_module.retrieve_system_document("personality", "personal")
        finally:
            _set_pool(original)

        assert result["document_content"] == "You are CLIVE."
        assert result["is_active"] is True

    @pytest.mark.asyncio
    async def test_raises_when_document_not_found(self):
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value=None)

        original = _get_original_pool()
        try:
            _set_pool(_make_mock_pool(mock_conn))
            with pytest.raises(ValueError, match="not found"):
                await retrieval_module.retrieve_system_document("personality", "personal")
        finally:
            _set_pool(original)

    @pytest.mark.asyncio
    async def test_fetches_by_version_id_when_provided(self):
        vid = uuid.uuid4()
        mock_row = {
            "document_content": "Doc content",
            "version_id": vid,
            "created_at": datetime.now(timezone.utc),
            "is_active": False,
        }
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value=mock_row)

        original = _get_original_pool()
        try:
            _set_pool(_make_mock_pool(mock_conn))
            result = await retrieval_module.retrieve_system_document(
                "personality", "personal", version_id=str(vid)
            )
        finally:
            _set_pool(original)

        assert result["is_active"] is False

    @pytest.mark.asyncio
    async def test_raises_when_pool_not_init(self):
        original = _get_original_pool()
        try:
            _set_pool(None)
            with pytest.raises(RuntimeError, match="not initialised"):
                await retrieval_module.retrieve_system_document("personality", "personal")
        finally:
            _set_pool(original)


# ---------------------------------------------------------------------------
# retrieve_document_by_filename
# ---------------------------------------------------------------------------

class TestRetrieveDocumentByFilename:
    @pytest.mark.asyncio
    async def test_returns_source_keys_and_chunk_count(self):
        mock_rows = [
            {"source_key": "uuid/report.pdf", "chunk_count": 5},
        ]
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value={"1": 1})  # zone valid
        mock_conn.fetch = AsyncMock(return_value=mock_rows)

        original = _get_original_pool()
        try:
            _set_pool(_make_mock_pool(mock_conn))
            result = await retrieval_module.retrieve_document_by_filename("report.pdf", "personal")
        finally:
            _set_pool(original)

        assert result["source_keys"] == ["uuid/report.pdf"]
        assert result["chunk_count"] == 5

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_match(self):
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value={"1": 1})  # zone valid
        mock_conn.fetch = AsyncMock(return_value=[])

        original = _get_original_pool()
        try:
            _set_pool(_make_mock_pool(mock_conn))
            result = await retrieval_module.retrieve_document_by_filename("missing.pdf", "personal")
        finally:
            _set_pool(original)

        assert result["source_keys"] == []
        assert result["chunk_count"] == 0


# ---------------------------------------------------------------------------
# retrieve_document_list
# ---------------------------------------------------------------------------

class TestRetrieveDocumentList:
    @pytest.mark.asyncio
    async def test_returns_documents(self):
        mock_rows = [
            {"source_key": "uuid/doc.pdf", "chunk_count": 10, "ingested_at": datetime.now(timezone.utc)},
        ]
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value={"1": 1})  # zone valid
        mock_conn.fetch = AsyncMock(return_value=mock_rows)

        original = _get_original_pool()
        try:
            _set_pool(_make_mock_pool(mock_conn))
            result = await retrieval_module.retrieve_document_list("personal")
        finally:
            _set_pool(original)

        assert result["total"] == 1
        assert result["documents"][0]["filename"] == "doc.pdf"

    @pytest.mark.asyncio
    async def test_returns_empty_for_unknown_zone(self):
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value=None)  # zone not found

        original = _get_original_pool()
        try:
            _set_pool(_make_mock_pool(mock_conn))
            result = await retrieval_module.retrieve_document_list("unknown_zone")
        finally:
            _set_pool(original)

        assert result["total"] == 0


# ---------------------------------------------------------------------------
# store_conversation_turn
# ---------------------------------------------------------------------------

class TestStoreConversationTurn:
    @pytest.mark.asyncio
    async def test_returns_early_when_pool_none(self):
        original = _get_original_pool()
        try:
            _set_pool(None)
            # Should not raise
            await retrieval_module.store_conversation_turn(
                event_id=uuid.uuid4(),
                conversation_id=uuid.uuid4(),
                role="user",
                content="hello",
            )
        finally:
            _set_pool(original)

    @pytest.mark.asyncio
    async def test_inserts_turn(self):
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()

        original = _get_original_pool()
        try:
            _set_pool(_make_mock_pool(mock_conn))
            await retrieval_module.store_conversation_turn(
                event_id=uuid.uuid4(),
                conversation_id=uuid.uuid4(),
                role="user",
                content="hello",
            )
        finally:
            _set_pool(original)

        mock_conn.execute.assert_called_once()


# ---------------------------------------------------------------------------
# get_conversation_history
# ---------------------------------------------------------------------------

class TestGetConversationHistory:
    @pytest.mark.asyncio
    async def test_returns_empty_when_pool_none(self):
        original = _get_original_pool()
        try:
            _set_pool(None)
            result = await retrieval_module.get_conversation_history(uuid.uuid4())
            assert result == []
        finally:
            _set_pool(original)

    @pytest.mark.asyncio
    async def test_returns_turns_chronologically(self):
        mock_rows = [
            {"role": "assistant", "content": "hello"},
            {"role": "user", "content": "hi"},
        ]  # DB returns DESC order; function reverses
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=mock_rows)

        original = _get_original_pool()
        try:
            _set_pool(_make_mock_pool(mock_conn))
            result = await retrieval_module.get_conversation_history(uuid.uuid4())
        finally:
            _set_pool(original)

        # Should be reversed (oldest first = chronological)
        assert result[0]["role"] == "user"
        assert result[1]["role"] == "assistant"


# ---------------------------------------------------------------------------
# retrieve_status
# ---------------------------------------------------------------------------

class TestRetrieveStatus:
    @pytest.mark.asyncio
    async def test_raises_when_pool_not_init(self):
        original = _get_original_pool()
        try:
            _set_pool(None)
            with pytest.raises(RuntimeError, match="not initialised"):
                await retrieval_module.retrieve_status("personal")
        finally:
            _set_pool(original)

    @pytest.mark.asyncio
    async def test_returns_status_metrics(self):
        now = datetime.now(timezone.utc)
        counts_row = {"doc_count": 3, "chunk_count": 60}
        last_doc_row = {"source_key": "uid/report.pdf", "ingested_at": now}
        last_query_row = {"created_at": now}
        spend_row = {"total_spend": 0.0431}

        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(side_effect=[counts_row, last_doc_row, last_query_row, spend_row])

        original = _get_original_pool()
        try:
            _set_pool(_make_mock_pool(mock_conn))
            result = await retrieval_module.retrieve_status("personal")
        finally:
            _set_pool(original)

        assert result["doc_count"] == 3
        assert result["chunk_count"] == 60
        assert result["last_doc_name"] == "report.pdf"
        assert result["llm_spend_today_usd"] == pytest.approx(0.0431)


# ---------------------------------------------------------------------------
# get_pending_actions
# ---------------------------------------------------------------------------

class TestGetPendingActions:
    @pytest.mark.asyncio
    async def test_raises_when_pool_not_init(self):
        original = _get_original_pool()
        try:
            _set_pool(None)
            with pytest.raises(RuntimeError, match="not initialised"):
                await retrieval_module.get_pending_actions("personal")
        finally:
            _set_pool(original)

    @pytest.mark.asyncio
    async def test_returns_pending_actions(self):
        rid = uuid.uuid4()
        cid = uuid.uuid4()
        now = datetime.now(timezone.utc)
        mock_rows = [
            {
                "action_request_id": rid,
                "action_type": "web.search",
                "action_target": "python",
                "action_description": "Search for python",
                "conversation_id": cid,
                "expires_at": now,
                "zone_scope": "personal",
                "created_at": now,
            }
        ]
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=mock_rows)

        original = _get_original_pool()
        try:
            _set_pool(_make_mock_pool(mock_conn))
            result = await retrieval_module.get_pending_actions("personal")
        finally:
            _set_pool(original)

        assert len(result) == 1
        assert result[0]["action_type"] == "web.search"
        assert result[0]["action_request_id"] == str(rid)
