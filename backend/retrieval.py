"""Nearest-neighbour search over one document's chunks — exact, by design.

Retrieval is always scoped to a single document, and a document has at most a
few hundred chunks (a 111-page PDF is on the order of 100). Ranking that many
768-float vectors exactly is a sub-millisecond scan of rows the
(document_id, chunk_index) index already finds. So this deliberately does NOT
use the HNSW index, for two measured reasons:

* Plain HNSW filters *after* the approximate search: it gathers `ef_search`
  (default 40) candidates from every document's chunks and then drops those
  from other documents. In the test with 600 closer chunks from other
  documents, that returned 0 of 5 rows.
* Iterative scanning (pgvector 0.8) fixes the count, but the search is still
  approximate: on the same data it put the document's best chunk first in only
  15 of 20 runs, because HNSW recall is below 1.

Exactness is forced by computing distances inside a MATERIALIZED CTE — an
optimisation fence the planner cannot push the ORDER BY through, so the HNSW
index is never chosen for this query whatever the table's statistics say.

The HNSW index stays on the table: it is what search *across* documents (a
user's whole library) would need, where exact scans would not scale.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import DocumentChunk


@dataclass(frozen=True)
class RetrievedChunk:
    chunk: DocumentChunk
    distance: float  # cosine distance, 0 = identical direction


def retrieve_chunks(
    db: Session, document_id: int, query_vector: Sequence[float], k: int
) -> List[RetrievedChunk]:
    """The `k` chunks of `document_id` closest to `query_vector`, nearest first.

    Only this document's chunks are ever returned. Ownership of the document is
    the caller's to check; this function trusts the id it is given.
    """
    if k <= 0:
        return []

    scored = (
        select(
            DocumentChunk.id.label("id"),
            DocumentChunk.embedding.cosine_distance(list(query_vector)).label("distance"),
        )
        .where(
            DocumentChunk.document_id == document_id,
            DocumentChunk.embedding.isnot(None),
        )
        .cte("scored")
        .prefix_with("MATERIALIZED")
    )
    ranked = db.execute(
        select(scored.c.id, scored.c.distance)
        .order_by(scored.c.distance, scored.c.id)
        .limit(k)
    ).all()
    if not ranked:
        return []

    by_id = {
        c.id: c
        for c in db.query(DocumentChunk).filter(DocumentChunk.id.in_([r.id for r in ranked]))
    }
    return [RetrievedChunk(chunk=by_id[r.id], distance=float(r.distance)) for r in ranked]
