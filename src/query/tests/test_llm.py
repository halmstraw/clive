"""Tests for query/llm.py — LiteLLM wrapper."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from query.llm import (
    _build_tools_section,
    embed,
    embed_batch,
    extract_entities,
    get_model,
    summarise_turns,
)
from query.registry import ToolDescriptor


# ---------------------------------------------------------------------------
# get_model
# ---------------------------------------------------------------------------

class TestGetModel:
    def test_returns_default_model(self):
        import os
        os.environ.pop("CLIVE_LLM_MODEL", None)
        model = get_model()
        assert "claude" in model.lower() or "anthropic" in model.lower()

    def test_returns_env_override(self):
        with patch.dict("os.environ", {"CLIVE_LLM_MODEL": "openai/gpt-4o"}):
            assert get_model() == "openai/gpt-4o"


# ---------------------------------------------------------------------------
# _build_tools_section
# ---------------------------------------------------------------------------

class TestBuildToolsSection:
    def test_empty_tools_returns_no_actions(self):
        result = _build_tools_section([])
        assert "No actions" in result

    def test_tools_listed_by_name_and_description(self):
        tools = [
            ToolDescriptor(tool_name="web_search", display_name="Web Search", description="Search the web"),
            ToolDescriptor(tool_name="reminder", display_name="Reminder", description="Set reminders"),
        ]
        result = _build_tools_section(tools)
        assert "web_search" in result
        assert "Search the web" in result
        assert "reminder" in result
        assert "Set reminders" in result
        assert "Available actions" in result

    def test_permission_scope_not_in_output(self):
        tools = [
            ToolDescriptor(
                tool_name="secret_tool",
                display_name="Secret Tool",
                description="Does things",
                permission_scope=["admin"],
            )
        ]
        result = _build_tools_section(tools)
        assert "admin" not in result
        assert "permission_scope" not in result


# ---------------------------------------------------------------------------
# embed
# ---------------------------------------------------------------------------

class TestEmbed:
    @pytest.mark.asyncio
    async def test_returns_embedding_list(self):
        mock_response = MagicMock()
        mock_response.data = [{"embedding": [0.1, 0.2, 0.3]}]

        with patch("query.llm.litellm.aembedding", AsyncMock(return_value=mock_response)):
            result = await embed("hello world")

        assert result == [0.1, 0.2, 0.3]

    @pytest.mark.asyncio
    async def test_passes_correct_model(self):
        mock_response = MagicMock()
        mock_response.data = [{"embedding": [0.0] * 1536}]

        mock_embed = AsyncMock(return_value=mock_response)
        with patch("query.llm.litellm.aembedding", mock_embed):
            await embed("test text")

        call_kwargs = mock_embed.call_args
        assert "text-embedding-3-small" in call_kwargs[1]["model"]


# ---------------------------------------------------------------------------
# embed_batch
# ---------------------------------------------------------------------------

class TestEmbedBatch:
    @pytest.mark.asyncio
    async def test_empty_input_returns_empty(self):
        result = await embed_batch([])
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_one_embedding_per_text(self):
        mock_response = MagicMock()
        mock_response.data = [
            {"embedding": [0.1, 0.2]},
            {"embedding": [0.3, 0.4]},
        ]

        with patch("query.llm.litellm.aembedding", AsyncMock(return_value=mock_response)):
            result = await embed_batch(["text1", "text2"])

        assert len(result) == 2
        assert result[0] == [0.1, 0.2]
        assert result[1] == [0.3, 0.4]


# ---------------------------------------------------------------------------
# extract_entities
# ---------------------------------------------------------------------------

class TestExtractEntities:
    @pytest.mark.asyncio
    async def test_extracts_valid_entities(self):
        entities = [
            {"entity_type": "person", "key": "colleague_name", "value": "Sarah"},
            {"entity_type": "preference", "key": "style", "value": "bullet points"},
        ]
        response_text = json.dumps({"entities": entities})

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = response_text

        with patch("query.llm.litellm.acompletion", AsyncMock(return_value=mock_response)):
            result = await extract_entities("I work with Sarah", "I see, Sarah is your colleague.")

        assert len(result) == 2
        assert result[0]["entity_type"] == "person"
        assert result[0]["key"] == "colleague_name"

    @pytest.mark.asyncio
    async def test_strips_json_code_fence(self):
        entities = [{"entity_type": "fact", "key": "city", "value": "London"}]
        fenced = f"```json\n{json.dumps({'entities': entities})}\n```"

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = fenced

        with patch("query.llm.litellm.acompletion", AsyncMock(return_value=mock_response)):
            result = await extract_entities("I live in London", "Great, London is a lovely city.")

        assert len(result) == 1
        assert result[0]["value"] == "London"

    @pytest.mark.asyncio
    async def test_filters_invalid_entity_types(self):
        entities = [
            {"entity_type": "invalid_type", "key": "something", "value": "val"},
            {"entity_type": "fact", "key": "valid_key", "value": "valid_val"},
        ]
        response_text = json.dumps({"entities": entities})

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = response_text

        with patch("query.llm.litellm.acompletion", AsyncMock(return_value=mock_response)):
            result = await extract_entities("hello", "world")

        # Only the valid entity type passes
        assert len(result) == 1
        assert result[0]["entity_type"] == "fact"

    @pytest.mark.asyncio
    async def test_returns_empty_on_llm_error(self):
        with patch("query.llm.litellm.acompletion", AsyncMock(side_effect=Exception("LLM failure"))):
            result = await extract_entities("hello", "world")

        assert result == []

    @pytest.mark.asyncio
    async def test_returns_empty_on_json_parse_error(self):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "not json at all"

        with patch("query.llm.litellm.acompletion", AsyncMock(return_value=mock_response)):
            result = await extract_entities("hello", "world")

        assert result == []

    @pytest.mark.asyncio
    async def test_filters_entities_missing_required_fields(self):
        entities = [
            {"entity_type": "fact"},  # missing key and value
            {"entity_type": "fact", "key": "city", "value": "London"},
        ]
        response_text = json.dumps({"entities": entities})

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = response_text

        with patch("query.llm.litellm.acompletion", AsyncMock(return_value=mock_response)):
            result = await extract_entities("hello", "world")

        assert len(result) == 1


# ---------------------------------------------------------------------------
# summarise_turns
# ---------------------------------------------------------------------------

class TestSummariseTurns:
    @pytest.mark.asyncio
    async def test_returns_summary_and_embedding(self):
        mock_completion_response = MagicMock()
        mock_completion_response.choices = [MagicMock()]
        mock_completion_response.choices[0].message.content = "This is a summary."

        embedding = [0.1] * 1536

        mock_embed_response = MagicMock()
        mock_embed_response.data = [{"embedding": embedding}]

        with (
            patch("query.llm.litellm.acompletion", AsyncMock(return_value=mock_completion_response)),
            patch("query.llm.litellm.aembedding", AsyncMock(return_value=mock_embed_response)),
        ):
            summary, emb = await summarise_turns("USER: hi\nASSISTANT: hello")

        assert summary == "This is a summary."
        assert len(emb) == 1536

    @pytest.mark.asyncio
    async def test_llm_failure_returns_fallback_summary(self):
        embedding = [0.0] * 1536
        mock_embed_response = MagicMock()
        mock_embed_response.data = [{"embedding": embedding}]

        with (
            patch("query.llm.litellm.acompletion", AsyncMock(side_effect=Exception("LLM down"))),
            patch("query.llm.litellm.aembedding", AsyncMock(return_value=mock_embed_response)),
        ):
            summary, emb = await summarise_turns("USER: hi\nASSISTANT: hello")

        assert "unavailable" in summary.lower() or "Consolidation" in summary

    @pytest.mark.asyncio
    async def test_embed_failure_returns_zero_vector(self):
        mock_completion_response = MagicMock()
        mock_completion_response.choices = [MagicMock()]
        mock_completion_response.choices[0].message.content = "Summary text."

        with (
            patch("query.llm.litellm.acompletion", AsyncMock(return_value=mock_completion_response)),
            patch("query.llm.litellm.aembedding", AsyncMock(side_effect=Exception("embed fail"))),
        ):
            summary, emb = await summarise_turns("USER: hi\nASSISTANT: hello")

        assert summary == "Summary text."
        assert len(emb) == 1536
        assert all(v == 0.0 for v in emb)


# ---------------------------------------------------------------------------
# complete
# ---------------------------------------------------------------------------

class TestComplete:
    @pytest.mark.asyncio
    async def test_returns_text_and_usage(self):
        from query.llm import complete

        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 100
        mock_usage.completion_tokens = 50

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Hello, I am CLIVE."
        mock_response.usage = mock_usage

        with patch("query.llm.litellm.acompletion", AsyncMock(return_value=mock_response)):
            text, usage = await complete(
                personality="You are CLIVE.",
                alignment_rules="Be safe.",
                conversation_history=[],
                retrieved_chunks=[],
                user_query="Hi",
            )

        assert text == "Hello, I am CLIVE."
        assert usage["prompt_tokens"] == 100
        assert usage["completion_tokens"] == 50

    @pytest.mark.asyncio
    async def test_includes_memory_entities_in_context(self):
        from query.llm import complete

        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 200
        mock_usage.completion_tokens = 100

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Response."
        mock_response.usage = mock_usage

        mock_acompletion = AsyncMock(return_value=mock_response)

        with patch("query.llm.litellm.acompletion", mock_acompletion):
            await complete(
                personality="",
                alignment_rules="",
                conversation_history=[],
                retrieved_chunks=[],
                user_query="hello",
                memory_entities=[{"entity_type": "person", "key": "colleague", "value": "Alice"}],
            )

        # Check memory entities were included in the messages
        call_messages = mock_acompletion.call_args[1]["messages"]
        user_message = [m for m in call_messages if m["role"] == "user"][0]
        assert "Memory" in user_message["content"] or "Alice" in user_message["content"]

    @pytest.mark.asyncio
    async def test_includes_retrieved_chunks(self):
        from query.llm import complete

        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 200
        mock_usage.completion_tokens = 100

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Response."
        mock_response.usage = mock_usage

        mock_acompletion = AsyncMock(return_value=mock_response)

        with patch("query.llm.litellm.acompletion", mock_acompletion):
            await complete(
                personality="",
                alignment_rules="",
                conversation_history=[],
                retrieved_chunks=[{"content": "Chunk text", "source_attribution": "doc.pdf"}],
                user_query="question",
            )

        call_messages = mock_acompletion.call_args[1]["messages"]
        user_message = [m for m in call_messages if m["role"] == "user"][0]
        assert "Chunk text" in user_message["content"]
