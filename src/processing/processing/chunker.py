"""Fixed-size token chunker — D-097.

512-token chunks, 50-token overlap, 50-token minimum.
Chunks below the minimum are merged with the preceding chunk.
Token count uses the cl100k_base tokeniser (text-embedding-3-small, D-096).
"""

from __future__ import annotations

import tiktoken

CHUNK_SIZE = 512
OVERLAP = 50
MIN_CHUNK = 50

_enc: tiktoken.Encoding | None = None


def _get_encoder() -> tiktoken.Encoding:
    global _enc
    if _enc is None:
        _enc = tiktoken.get_encoding("cl100k_base")
    return _enc


def chunk_text(text: str) -> list[str]:
    """Split text into overlapping token chunks and return as strings."""
    enc = _get_encoder()
    tokens = enc.encode(text)

    if not tokens:
        return []

    chunks: list[list[int]] = []
    start = 0

    while start < len(tokens):
        end = min(start + CHUNK_SIZE, len(tokens))
        chunks.append(tokens[start:end])
        if end == len(tokens):
            break
        start += CHUNK_SIZE - OVERLAP

    # Merge trailing chunks below the minimum size into their predecessor.
    merged: list[list[int]] = []
    for chunk in chunks:
        if merged and len(chunk) < MIN_CHUNK:
            merged[-1] = merged[-1] + chunk
        else:
            merged.append(chunk)

    return [enc.decode(c) for c in merged]
