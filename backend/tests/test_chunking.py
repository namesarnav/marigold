"""Unit tests for backend/chunking.py — pure functions, no database needed."""

import fitz
import pytest

from backend.chunking import (
    CHARS_PER_TOKEN,
    chunk_pages,
    estimate_tokens,
    extract_pages,
    strip_nul,
)


def _numbered_words(prefix, count):
    """Distinct, sentence-free words so overlaps can be located exactly.

    Each word is 7 characters (+1 space) = 2 estimated tokens.
    """
    return " ".join(f"{prefix}{i:05d}" for i in range(count))


def _pdf(pages):
    doc = fitz.open()
    for text in pages:
        page = doc.new_page()
        if text:
            page.insert_textbox(fitz.Rect(36, 36, 576, 806), text, fontsize=6)
    data = doc.tobytes()
    doc.close()
    return data


# --- extraction ---------------------------------------------------------------


def test_extract_pages_keeps_one_entry_per_page_including_empty_ones():
    pages = extract_pages(_pdf(["first page", "", "third page"]))
    assert len(pages) == 3
    assert "first page" in pages[0]
    assert pages[1].strip() == ""
    assert "third page" in pages[2]


def test_strip_nul_drops_nul_without_substituting():
    assert strip_nul("a\x00b\x00\x00c") == "abc"
    assert strip_nul("plain") == "plain"


# --- chunking -----------------------------------------------------------------


def test_no_text_means_no_chunks():
    assert chunk_pages([]) == []
    assert chunk_pages(["", "   \n\t", ""]) == []


def test_short_document_is_a_single_chunk():
    chunks = chunk_pages(["Photosynthesis converts light into chemical energy."])
    assert len(chunks) == 1
    assert chunks[0].chunk_index == 0
    assert (chunks[0].page_start, chunks[0].page_end) == (1, 1)
    assert chunks[0].text == "Photosynthesis converts light into chemical energy."
    assert chunks[0].token_count == estimate_tokens(chunks[0].text)


def test_chunks_respect_max_and_reach_target():
    # 2000 words x 2 tokens = 4000 estimated tokens, with no sentence ends.
    chunks = chunk_pages([_numbered_words("w", 2000)], target_tokens=650, max_tokens=800,
                         overlap_tokens=100)
    assert len(chunks) > 1
    for c in chunks:
        assert c.token_count <= 800 + 1  # +1: the per-text estimate rounds up
    # Every chunk but the last is filled to the maximum when no sentence end
    # offers an earlier break.
    for c in chunks[:-1]:
        assert c.token_count >= 650


def test_consecutive_chunks_overlap_by_about_the_overlap_budget():
    chunks = chunk_pages([_numbered_words("w", 2000)], target_tokens=650, max_tokens=800,
                         overlap_tokens=100)
    for a, b in zip(chunks, chunks[1:]):
        a_words = a.text.split()
        b_words = b.text.split()
        # b starts somewhere inside a, and everything from there to a's end is
        # repeated verbatim at b's start.
        start = a_words.index(b_words[0])
        shared = a_words[start:]
        assert b_words[: len(shared)] == shared
        shared_tokens = estimate_tokens(" ".join(shared))
        assert 100 <= shared_tokens <= 100 + 3  # one word's worth of slack


def test_every_word_appears_in_some_chunk_in_order():
    words = _numbered_words("w", 1500).split()
    chunks = chunk_pages([" ".join(words)], target_tokens=200, max_tokens=300, overlap_tokens=50)
    seen = []
    for c in chunks:
        for w in c.text.split():
            if not seen or w > seen[-1]:
                seen.append(w)
    assert seen == words


def test_prefers_to_end_on_a_sentence_once_past_target():
    sentence = "word " * 59 + "end."  # 60 words = 120 tokens, ends a sentence
    text = " ".join([sentence] * 20)
    chunks = chunk_pages([text], target_tokens=200, max_tokens=400, overlap_tokens=20)
    for c in chunks[:-1]:
        assert c.text.endswith("end.")


def test_page_mapping_across_a_page_break():
    page1 = _numbered_words("a", 300)  # 600 tokens
    page2 = _numbered_words("b", 300)
    chunks = chunk_pages([page1, page2], target_tokens=650, max_tokens=800, overlap_tokens=100)

    first = chunks[0]
    assert (first.page_start, first.page_end) == (1, 2)  # 600 + 100 crosses into page 2
    assert first.text.startswith("a00000")
    assert "b00000" in first.text

    for c in chunks:
        words = c.text.split()
        expected_start = 1 if words[0].startswith("a") else 2
        expected_end = 1 if words[-1].startswith("a") else 2
        assert (c.page_start, c.page_end) == (expected_start, expected_end)


def test_empty_pages_are_skipped_but_do_not_shift_page_numbers():
    chunks = chunk_pages(["", "alpha beta.", "", "", "gamma delta."])
    assert len(chunks) == 1
    assert (chunks[0].page_start, chunks[0].page_end) == (2, 5)
    assert chunks[0].text == "alpha beta. gamma delta."

    small = chunk_pages(["", _numbered_words("p", 400), "", _numbered_words("q", 400)],
                        target_tokens=300, max_tokens=400, overlap_tokens=50)
    pages_used = {p for c in small for p in (c.page_start, c.page_end)}
    assert pages_used <= {2, 4}
    assert small[0].page_start == 2 and small[-1].page_end == 4


def test_nul_bytes_never_reach_a_chunk():
    chunks = chunk_pages(["Chap\x00ter one\x00.", "\x00\x00", "more\x00 text"])
    assert len(chunks) == 1
    assert "\x00" not in chunks[0].text
    assert chunks[0].text == "Chapter one. more text"
    # The NUL-only page counts as empty.
    assert (chunks[0].page_start, chunks[0].page_end) == (1, 3)


def test_a_word_larger_than_the_maximum_is_taken_alone():
    blob = "x" * (900 * CHARS_PER_TOKEN)
    chunks = chunk_pages([f"before {blob} after"], target_tokens=650, max_tokens=800,
                         overlap_tokens=100)
    assert [c.text for c in chunks].count(blob) == 1
    assert chunks[-1].text.endswith("after")


def test_chunk_indexes_are_sequential():
    chunks = chunk_pages([_numbered_words("w", 3000)])
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))


@pytest.mark.parametrize(
    "target,maximum,overlap",
    [(650, 600, 100), (100, 800, 100), (100, 800, 200), (100, 800, -1)],
)
def test_invalid_sizes_are_rejected(target, maximum, overlap):
    with pytest.raises(ValueError):
        chunk_pages(["text"], target_tokens=target, max_tokens=maximum, overlap_tokens=overlap)


def test_upload_stores_chunks_with_page_ranges(client, auth_headers):
    from conftest import _TestSession, upload_doc

    from backend.models import DocumentChunk

    pdf = _pdf([_numbered_words("a", 300), "", _numbered_words("c", 300)])
    doc_id = upload_doc(client, auth_headers, pdf)

    db = _TestSession()
    try:
        rows = (
            db.query(DocumentChunk)
            .filter(DocumentChunk.document_id == doc_id)
            .order_by(DocumentChunk.chunk_index)
            .all()
        )
    finally:
        db.close()
    assert rows
    assert rows[0].page_start == 1
    assert rows[-1].page_end == 3
    assert all(r.page_start in (1, 3) and r.page_end in (1, 3) for r in rows)
    assert all(r.token_count > 0 for r in rows)
