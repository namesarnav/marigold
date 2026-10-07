# Card generation

How Marigold turns a PDF into flashcards, in both modes, and how the two are
compared. The README has the short version and the env vars.

```
upload ─┬─ extract text per page (PyMuPDF, NUL bytes stripped)
        ├─ documents.extracted_text = pages joined          ← full mode reads this
        └─ document_chunks: ~650-token windows, 100 overlap,
           page_start/page_end                              ← same transaction as the document
                │
        background task
                ├─ embed chunks (gemini-embedding-2, 768-d)  ← both modes; non-fatal in full
                └─ draft_cards(GENERATION_MODE)
                     full: one call over the whole text
                     rag:  topics ─► per topic: embed query ─► top-k chunks of THIS document
                                     ─► one call per topic, cards cite chunk ids
                                     ─► drop cards citing ids they were not shown
                └─ save_cards: flashcards + flashcard_sources + concepts
```

## Chunking — `backend/chunking.py`

Text is extracted page by page, so each chunk knows the pages it spans. Words
are packed into windows of about `CHUNK_TARGET_TOKENS` (650). A window goes past
the target only to finish a sentence, and never past `CHUNK_MAX_TOKENS` (800).
The next window starts `CHUNK_OVERLAP_TOKENS` (100) before the previous one
ended, so a fact that straddles a boundary is wholly inside at least one chunk.
Empty pages add nothing, but later pages keep their real numbers.

Sizes are **estimated** tokens, at Google's rule of thumb of four characters per
token. An exact count would cost a `count_tokens` API call per chunk, for a
number that only decides where windows end. `document_chunks.token_count`
stores the same estimate.

## Embeddings — `backend/embeddings.py`

`gemini-embedding-2` at 768 dimensions (`EMBEDDING_DIM`). It is 768 rather than
the native 3072 because pgvector's HNSW index on `vector` is capped at 2000
dimensions. Google trains these models to be truncated (Matryoshka) and lists
768 among its recommended sizes. Its only published MTEB figures by dimension
are for `gemini-embedding-001` (768: 67.99, 1536: 68.17). None were found for
`gemini-embedding-2`, so Recall@k from the eval is the number to trust here.

Two traps in this model, both covered by tests:

- **A list of strings is not a batch.** `contents=[a, b, c]` returns *one*
  aggregated embedding. Each text is wrapped in its own `Content`, and the number
  of vectors returned is checked against the number sent.
- **No `task_type`.** The model rejects it. Retrieval prefixes go in the text
  instead (`task: search result | query: …`, `title: none | text: …`).

Requests are batched (`EMBEDDING_BATCH_SIZE`). 429, 5xx and transport errors are
retried with full-jitter exponential backoff (up to 6 attempts, capped at 30s).
Any other 4xx fails at once. The API image gains only the `pgvector` package
(pure Python, no numpy); there is no local model and no PyTorch.

## Storage

| Table | |
| --- | --- |
| `document_chunks` | `document_id` → documents **ON DELETE CASCADE**, `chunk_index`, `page_start`, `page_end`, `text`, `token_count`, `embedding vector(768)`. HNSW index (`vector_cosine_ops`); unique `(document_id, chunk_index)` |
| `flashcard_sources` | `(flashcard_id → CASCADE, chunk_id → CASCADE)`, the citations |

Neither table is referenced by `interactions`. Deleting a card or a document
removes its citations and chunks in the database. Interaction history is
untouched: `interactions.flashcard_id` stays `ON DELETE SET NULL`. Cards are
still deleted one row at a time through the ORM, never with a bulk
`query().delete()`, which skips the `quiz_answers` cascade (see
`generation.delete_cards`).

## Retrieval — `backend/retrieval.py`

The top-k chunks of one document by cosine distance. The search is **exact**,
and deliberately bypasses the HNSW index. The reasons were measured in
`backend/tests/test_retrieval.py`, with 600 closer chunks from 30 other
documents in the table:

| Plan | Rows returned (k=5) | Document's best chunk ranked first |
| --- | --- | --- |
| HNSW, plain | 0 of 5 | n/a |
| HNSW, `hnsw.iterative_scan = strict_order` | 5 of 5 | 15 of 20 runs |
| Exact (current) | 5 of 5 | always |

Plain HNSW filters *after* its approximate search, so a per-document query
starves when other documents crowd the neighbourhood. Iterative scanning fixes
the count, but the search is still approximate. A document has at most a few
hundred chunks, so ranking them exactly is cheap. Distances are computed inside
a `MATERIALIZED` CTE, which the planner cannot answer from the HNSW index. A
test checks the plan, and fails if the fence is removed. The HNSW index stays
for search *across* documents, where exact scans would not scale.

## Generation — `backend/generation.py`

**Topics.** Gemini reads chunks sampled evenly across the document, up to ~12k
estimated tokens, and names `RAG_TOPIC_COUNT` distinct, searchable topics. It
samples instead of reading everything because sending everything is the cost
this mode exists to avoid. Spreading the sample evenly keeps the back of long
documents represented. The PDF outline would make a good hint, but the PDF bytes
are not kept after upload, so regenerate could not use it and the two entry
points would disagree.

**Cards.** Each topic is embedded as a query, its `RAG_TOP_K` nearest chunks are
retrieved, and one call (at most 3 at once) writes cards from only those chunks.
Each card returns `source_chunk_ids`. A card is **dropped** if it cites nothing,
or cites any id it was not shown. It is not repaired: an invented id means the
model was not grounded in what it was given, so the card's content is no more
trustworthy than its citation. Rejections are logged.

**Assembly.** Each topic is asked for ⌈N/topics⌉+1 cards. Cards are taken
round-robin across topics, deduplicated by question, and capped at
`CARDS_PER_UPLOAD`. A few rejections therefore don't shorten the deck, and no
single topic dominates.

**Regenerate** drafts first and swaps second. The old cards are deleted only in
the transaction that inserts the new ones, so a failure (rate limit, bad JSON,
every card rejected) leaves the existing deck as it was.

**Fallback.** Documents uploaded before chunking existed have no chunks, and
their page boundaries were never stored. `rag` generates them with `full` and
logs it. Re-uploading gives them chunks.

## API and UI

`FlashcardOut.sources` is `[{chunk_id, page_start, page_end, snippet}]`, and the
quiz review payload carries the same field per question. The snippet is the
start of the cited chunk (240 characters, cut at a word), never text the model
wrote, so it cannot misquote the source. Live quiz questions omit sources,
because the passage would give the answer away. Study mode shows "From page N"
under the card once it is flipped, and quiz review shows it under each question.
Cards with no sources (full mode, hand-written) show nothing.

## Evaluation

`scripts/eval_rag.py` runs both modes over `eval/docs/*.pdf`. Every figure in
its report is either measured or `null` with a reason.

| Metric | Measured as | Null when |
| --- | --- | --- |
| Recall@k | share of labelled queries where any top-k chunk spans a labelled answer page (`eval/labels.json`) | full mode (no retrieval); no filled labels |
| Faithfulness | share of judged cards a Gemini judge finds fully supported by **their cited chunks only** | full mode (no citations); `--no-judge` |
| Tokens / upload | sum of the API's `usage_metadata` (prompt + output + thinking) over generation calls | any call missing a count |
| Embedding tokens / upload | reported separately, **estimated**, since the embedding API returns no usage | — |
| Cost / upload | tokens × prices passed on the command line; thinking at the output rate | no prices supplied |
| Latency p50/p95 | wall time of post-upload generation (rag includes embedding), nearest rank, with n | no successful runs; p95 flagged when n < 20 |

The judge is a Gemini model grading Gemini output, so its score is a screen,
not a verdict. Each report therefore includes `manual_sample.json`: 20 seeded
random cards, with their sources, and blank fields for checking by hand. Judge
calls are tracked separately and never counted as upload cost.

## Known limitations

- In `full` mode every upload still pays for embedding its chunks, so the
  document can later be regenerated in `rag`. That cost shows up as embedding
  tokens, not in the full-mode generation figures.
- Editing a card's answer keeps its citations, which may then no longer match.
- Regenerating deletes `quiz_answers` rows for the old cards (an ORM cascade
  that predates this work). Quiz scores and interactions survive, but a past
  quiz's per-question review loses those questions.
