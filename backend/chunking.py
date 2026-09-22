"""Split a PDF's text into overlapping, page-attributed chunks for retrieval.

Text is extracted page by page, so every chunk knows the pages it came from;
joining the pages first (as the full-document path does) would lose that.

Sizes are in *estimated* tokens. An exact count needs Gemini's count_tokens
endpoint — one network call per chunk, at upload time — for a number that only
steers where windows end. The estimate is Google's own rule of thumb, about four
characters per token for English, applied per word so a window can end on a
word boundary. Stored `token_count`s are this estimate and are labelled as such
wherever they are reported; real token usage for cost accounting comes from the
API's usage metadata, not from here.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Sequence

import fitz  # PyMuPDF

# Postgres rejects NUL in text columns outright: "PostgreSQL text fields cannot
# contain NUL (0x00) bytes". Real PDFs do contain them — broken embedded fonts
# and odd encodings both produce NUL in extracted text — so an upload of a
# perfectly readable document failed at the INSERT with a 500, and, because the
# server tore the connection down mid-body, the browser reported it as the far
# less helpful "Failed to fetch".
_NUL = "\x00"

CHARS_PER_TOKEN = 4
_SENTENCE_END = (".", "?", "!", ":", ";")


def strip_nul(text: str) -> str:
    """Remove NUL bytes from extracted text.

    Dropped rather than replaced. A NUL in a PDF text layer carries no meaning —
    it is an artefact of the encoding, not a character the author wrote — so
    substituting a space or U+FFFD would insert content that was never there,
    into the text a language model then reads.
    """
    return text.replace(_NUL, "") if _NUL in text else text


def extract_pages(file_bytes: bytes) -> List[str]:
    """Text of each page, in order, NUL-free. Index 0 is page 1."""
    with fitz.open(stream=file_bytes, filetype="pdf") as doc:
        return [strip_nul(page.get_text()) for page in doc]


def estimate_tokens(text: str) -> int:
    return math.ceil(len(text) / CHARS_PER_TOKEN) if text else 0


@dataclass(frozen=True)
class Chunk:
    chunk_index: int
    page_start: int  # 1-based, inclusive
    page_end: int  # 1-based, inclusive
    text: str
    token_count: int  # estimated; see module docstring


@dataclass(frozen=True)
class _Word:
    text: str
    page: int
    # Characters this word costs in the joined chunk text, including its
    # separating space. Windows are measured in characters and converted at
    # CHARS_PER_TOKEN, so the sizes the chunker aims for and the token_count it
    # stores are the same estimate. (Rounding each word up to whole tokens
    # instead overstated short words by up to 4x.)
    chars: int


def _words(pages: Sequence[str]) -> List[_Word]:
    words: List[_Word] = []
    for number, page_text in enumerate(pages, start=1):
        # Empty and whitespace-only pages contribute nothing, so no chunk ever
        # claims to start or end on one; the numbering of later pages is
        # unaffected because it comes from the page's position, not a counter.
        for word in strip_nul(page_text).split():
            words.append(_Word(word, number, len(word) + 1))
    return words


def chunk_pages(
    pages: Sequence[str],
    target_tokens: int = 650,
    max_tokens: int = 800,
    overlap_tokens: int = 100,
) -> List[Chunk]:
    """Pack words into windows of about `target_tokens`, never over `max_tokens`.

    A window is extended past the target only to reach the end of a sentence,
    and stops at `max_tokens` regardless, so chunks read as whole thoughts where
    the text allows it without ever growing unbounded. Each window after the
    first starts `overlap_tokens` back from where the previous one ended, so a
    fact straddling a boundary is wholly inside at least one chunk.

    Returns [] when the pages hold no text at all.
    """
    if not 0 <= overlap_tokens < target_tokens <= max_tokens:
        raise ValueError("need 0 <= overlap_tokens < target_tokens <= max_tokens")

    words = _words(pages)
    # The joined text has one fewer space than the words' costs sum to, which
    # only ever makes a window one character smaller than budgeted.
    target_chars = target_tokens * CHARS_PER_TOKEN
    max_chars = max_tokens * CHARS_PER_TOKEN
    overlap_chars = overlap_tokens * CHARS_PER_TOKEN
    chunks: List[Chunk] = []
    start = 0
    n = len(words)

    while start < n:
        end = start
        total = 0
        while end < n and total + words[end].chars <= max_chars + 1:
            total += words[end].chars
            end += 1
            if total >= target_chars and words[end - 1].text.endswith(_SENTENCE_END):
                break
        if end == start:
            # A single "word" larger than max_tokens (a base64 blob, a URL with
            # no spaces). Take it alone rather than loop forever.
            end += 1

        window = words[start:end]
        text = " ".join(w.text for w in window)
        chunks.append(
            Chunk(
                chunk_index=len(chunks),
                page_start=window[0].page,
                page_end=window[-1].page,
                text=text,
                token_count=estimate_tokens(text),
            )
        )
        if end >= n:
            break

        # Step back from the end until the overlap budget is spent. Never back
        # to (or before) this window's own start, so every iteration advances.
        back = end
        carried = 0
        while back > start + 1 and carried < overlap_chars:
            back -= 1
            carried += words[back].chars
        start = back

    return chunks
