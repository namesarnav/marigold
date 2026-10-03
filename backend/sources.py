"""Serialise a flashcard's citations for the API."""

from __future__ import annotations

from typing import List

from .models import Flashcard
from .schemas import SourceOut

SNIPPET_CHARS = 240


def snippet(text: str, limit: int = SNIPPET_CHARS) -> str:
    """The start of a chunk, cut at a word boundary."""
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[:limit]
    space = cut.rfind(" ")
    if space > limit // 2:
        cut = cut[:space]
    return cut.rstrip(" ,;:") + "…"


def sources_for(card: Flashcard) -> List[SourceOut]:
    """Citations in reading order (by page, then position in the document)."""
    chunks = sorted(
        (s.chunk for s in card.sources if s.chunk is not None),
        key=lambda c: (c.page_start, c.chunk_index),
    )
    return [
        SourceOut(
            chunk_id=c.id,
            page_start=c.page_start,
            page_end=c.page_end,
            snippet=snippet(c.text),
        )
        for c in chunks
    ]
