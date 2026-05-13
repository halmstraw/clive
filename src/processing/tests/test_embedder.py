"""Tests for Block 15 embedder — D-096."""
from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestEmbedBatch:
    async def test_empty_list_returns_empty(self):
        from processing.embedder import embed_batch

        result = await embed_batch([])
        assert result == []

    async def test_returns_one_vector_per_input(self):
        from processing.embedder import embed_batch

        mock_response = MagicMock()
        mock_response.data = [
            {"embedding": [0.1, 0.2, 0.3]},
            {"embedding": [0.4, 0.5, 0.6]},
        ]
        with patch("processing.embedder.litellm.embedding", return_value=mock_response):
            result = await embed_batch(["text one", "text two"])

        assert len(result) == 2
        assert result[0] == [0.1, 0.2, 0.3]
        assert result[1] == [0.4, 0.5, 0.6]

    async def test_single_text_returns_single_vector(self):
        from processing.embedder import embed_batch

        mock_response = MagicMock()
        mock_response.data = [{"embedding": [1.0, 2.0]}]
        with patch("processing.embedder.litellm.embedding", return_value=mock_response):
            result = await embed_batch(["only one"])

        assert len(result) == 1
        assert result[0] == [1.0, 2.0]

    async def test_litellm_called_with_configured_model(self):
        from processing import embedder
        from processing.embedder import embed_batch

        mock_response = MagicMock()
        mock_response.data = [{"embedding": [0.0]}]
        with patch("processing.embedder.litellm.embedding", return_value=mock_response) as mock_embed:
            await embed_batch(["hello"])

        mock_embed.assert_called_once()
        call_kwargs = mock_embed.call_args
        assert call_kwargs[1]["model"] == embedder.EMBEDDING_MODEL
        assert call_kwargs[1]["input"] == ["hello"]
