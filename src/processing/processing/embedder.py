"""Embedding via LiteLLM — D-096.

Model: text-embedding-3-small (1536 dimensions).
Provider and model are env-configurable; defaults match D-096.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

import litellm
import structlog

log = structlog.get_logger()

EMBEDDING_MODEL = os.environ.get("CLIVE_EMBEDDING_MODEL", "text-embedding-3-small")


async def embed_batch(texts: list[str]) -> list[list[float]]:
    """Return embedding vectors for each text string.

    Runs LiteLLM's synchronous embedding call in a thread pool so the
    event loop is not blocked.
    """
    if not texts:
        return []

    def _call() -> Any:
        return litellm.embedding(model=EMBEDDING_MODEL, input=texts)

    loop = asyncio.get_running_loop()
    response = await loop.run_in_executor(None, _call)
    vectors = [item["embedding"] for item in response.data]
    log.info("embeddings_generated", model=EMBEDDING_MODEL, count=len(vectors))
    return vectors
