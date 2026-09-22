"""Text embeddings through the Gemini API, batched and retried.

Two things about `gemini-embedding-2` shape this module and are easy to get
wrong:

* **A list of strings is NOT a batch.** Passed as `contents=[a, b, c]`, the
  model returns *one aggregated embedding* for all three. Each text has to be
  wrapped in its own `Content` to get one vector per text. `_call_embed_api`
  does that, and `embed_texts` checks the count that comes back, so a regression
  here fails loudly instead of storing the same vector for every chunk.
* **No `task_type`.** The model rejects it; the retrieval task is written into
  the text instead, with the prefixes Google documents for asymmetric search
  (`task: search result | query: …` for queries, `title: … | text: …` for
  documents).

Vectors are requested at EMBEDDING_DIM and L2-normalised here. The model
normalises truncated outputs itself, but cosine distance in pgvector assumes
nothing, and normalising twice is free.
"""

from __future__ import annotations

import logging
import math
import time
from typing import Callable, List, Optional, Sequence

import anyio
from google.genai import types

from . import usage
from .chunking import estimate_tokens
from .config import EMBEDDING_DIM, get_settings
from .retry import (  # noqa: F401  (re-exported: tests and callers use these names)
    BASE_DELAY_SECONDS,
    MAX_ATTEMPTS,
    MAX_DELAY_SECONDS,
    RETRYABLE_STATUS,
    backoff_delay as _backoff_delay,
    with_retry as _with_retry,
)

logger = logging.getLogger(__name__)


class EmbeddingError(RuntimeError):
    pass


def document_input(text: str, title: Optional[str] = None) -> str:
    return f"title: {title or 'none'} | text: {text}"


def query_input(text: str) -> str:
    return f"task: search result | query: {text}"


def _client():
    # Imported at call time so the test suite's network guard, which replaces
    # genai.Client, is always the one constructed.
    from google import genai

    return genai.Client(api_key=get_settings().gemini_api_key)


def _call_embed_api(client, model: str, texts: Sequence[str], dim: int) -> List[List[float]]:
    """One embed_content request. The only function here that touches the network."""
    response = client.models.embed_content(
        model=model,
        contents=[types.Content(parts=[types.Part(text=t)]) for t in texts],
        config=types.EmbedContentConfig(output_dimensionality=dim),
    )
    return [list(e.values) for e in (response.embeddings or [])]


def _normalise(vector: Sequence[float]) -> List[float]:
    norm = math.sqrt(sum(v * v for v in vector))
    if norm == 0:
        raise EmbeddingError("the embedding API returned a zero vector")
    return [v / norm for v in vector]


def embed_texts(
    texts: Sequence[str],
    *,
    client=None,
    batch_size: Optional[int] = None,
    sleep: Callable[[float], None] = time.sleep,
) -> List[List[float]]:
    """Embed already-prefixed texts, in order, one normalised vector each."""
    if not texts:
        return []
    settings = get_settings()
    client = client or _client()
    size = batch_size or settings.embedding_batch_size
    vectors: List[List[float]] = []

    for offset in range(0, len(texts), size):
        batch = list(texts[offset: offset + size])
        started = time.perf_counter()
        result = _with_retry(
            lambda: _call_embed_api(client, settings.gemini_embedding_model, batch, EMBEDDING_DIM),
            sleep,
            what="Embedding request",
        )
        usage.record(usage.CallRecord(
            kind="embed",
            model=settings.gemini_embedding_model,
            latency_seconds=time.perf_counter() - started,
            estimated_input_tokens=sum(estimate_tokens(t) for t in batch),
        ))
        if len(result) != len(batch):
            raise EmbeddingError(
                f"asked for {len(batch)} embeddings, got {len(result)}; the inputs "
                "may have been aggregated into one (see module docstring)"
            )
        for vector in result:
            if len(vector) != EMBEDDING_DIM:
                raise EmbeddingError(
                    f"expected {EMBEDDING_DIM}-dimensional embeddings, got {len(vector)}"
                )
            vectors.append(_normalise(vector))
    return vectors


def embed_documents(texts: Sequence[str], **kwargs) -> List[List[float]]:
    return embed_texts([document_input(t) for t in texts], **kwargs)


def embed_query(text: str, **kwargs) -> List[float]:
    return embed_texts([query_input(text)], **kwargs)[0]


async def aembed_documents(texts: Sequence[str]) -> List[List[float]]:
    # The SDK call is blocking I/O; keep it off the event loop, like the
    # generation call in gemini.py.
    return await anyio.to_thread.run_sync(lambda: embed_documents(texts))


async def aembed_query(text: str) -> List[float]:
    return await anyio.to_thread.run_sync(lambda: embed_query(text))


async def embed_document_chunks(db, document) -> int:
    """Fill in missing embeddings for a document's chunks. Returns how many.

    Idempotent: chunks that already have a vector are skipped, so a retry after
    a partial failure only pays for what is left. Flushes, does not commit.
    """
    pending = [c for c in document.chunks if c.embedding is None]
    if not pending:
        return 0
    vectors = await aembed_documents([c.text for c in pending])
    for chunk, vector in zip(pending, vectors):
        chunk.embedding = vector
    db.flush()
    return len(pending)
