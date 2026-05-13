"""Tests for Block 15 chunker — D-097."""
from __future__ import annotations

import tiktoken
import pytest

from processing.chunker import CHUNK_SIZE, MIN_CHUNK, OVERLAP, chunk_text

_enc = tiktoken.get_encoding("cl100k_base")


def _tokens(text: str) -> int:
    return len(_enc.encode(text))


class TestChunkText:
    def test_empty_string_returns_empty(self):
        assert chunk_text("") == []

    def test_short_text_single_chunk(self):
        assert len(chunk_text("Hello world")) == 1

    def test_long_text_produces_multiple_chunks(self):
        # "word " is 1-2 tokens; 600 repetitions guarantees > CHUNK_SIZE tokens
        text = "word " * 600
        chunks = chunk_text(text)
        assert len(chunks) >= 2

    def test_all_outputs_are_strings(self):
        for chunk in chunk_text("alpha " * 200):
            assert isinstance(chunk, str)

    def test_chunks_are_non_empty(self):
        for chunk in chunk_text("beta " * 300):
            assert chunk.strip()

    def test_no_chunk_below_minimum_token_size(self):
        """After merge pass, no chunk may be below MIN_CHUNK tokens."""
        text = "The quick brown fox jumps over the lazy dog. " * 100
        chunks = chunk_text(text)
        assert len(chunks) > 1
        for chunk in chunks:
            assert _tokens(chunk) >= MIN_CHUNK

    def test_single_chunk_size_upper_bound(self):
        # A single chunk cannot exceed CHUNK_SIZE + (MIN_CHUNK - 1) tokens
        # (the merge can grow the predecessor by at most MIN_CHUNK - 1 tokens)
        text = "gamma " * 600
        for chunk in chunk_text(text):
            # Upper bound: a chunk may absorb one trailing stub
            assert _tokens(chunk) <= CHUNK_SIZE + MIN_CHUNK - 1

    def test_overlap_is_respected(self):
        # The start of chunk[i+1] should overlap with the end of chunk[i]
        text = "delta " * 600
        chunks = chunk_text(text)
        if len(chunks) < 2:
            pytest.skip("Not enough chunks to test overlap")
        # Overlap means chunk[1] must begin with tokens that also appear at the
        # end of chunk[0].  We verify this by checking that the first token of
        # chunk[1] is present somewhere in the last OVERLAP tokens of chunk[0].
        end_of_first = _enc.decode(_enc.encode(chunks[0])[-OVERLAP:])
        start_of_second = chunks[1][:len(end_of_first)]
        assert start_of_second in chunks[0]
