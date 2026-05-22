"""Cluster flashcard embeddings into concepts.

## Which algorithm, and the tradeoff

**Agglomerative clustering with a cosine distance threshold**, not HDBSCAN.

The two differ in what they assume about the data:

- *HDBSCAN* finds variable-density clusters and labels sparse points as noise
  (`-1`). That noise label is the problem here. Every flashcard must map to
  some concept, because a card with no concept produces interactions that the
  knowledge tracer cannot attribute to anything. A one-off card about an
  unusual topic is a legitimate concept of size one, not noise to discard.
  HDBSCAN also needs a reasonable number of points before density estimation
  means anything; a user's first upload might be 15 cards.

- *Agglomerative with a distance threshold* has neither property. It assigns
  every point, produces singleton clusters naturally, and — crucially — the
  knob is a **cosine distance threshold**, which is directly interpretable:
  "cards closer than this are the same concept". That is a parameter a person
  can reason about and tune by looking at examples, unlike `min_cluster_size`
  and `min_samples`, which interact in ways that are hard to predict.

The cost of that choice: agglomerative clustering is O(n²) in memory. At
Marigold's scale (a user's library is thousands of cards at the very most) that
is irrelevant. If a single user ever reaches ~50k cards this becomes the
bottleneck and HDBSCAN, or a two-stage approach, would be worth revisiting.

`n_clusters` is deliberately not a parameter. The number of concepts in a
document is not something a user knows in advance, and forcing a count would
split coherent topics or merge unrelated ones to hit a quota.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence

import numpy as np

# Cards closer than this in cosine distance are treated as testing the same
# idea. Calibrated, not guessed — `python -m ml.concepts.calibrate` reproduces
# the measurement across labelled samples of flashcard text:
#
#   sample     within-topic distance      between-topic distance   largest pure
#   broad-11   min .265 mean .526 max .703  min .433 mean .851        0.55
#   sparse-7   min .265 mean .451 max .513  min .433 mean .774        0.45
#
# Two things that measurement showed, both worth knowing before touching this:
#
# 1. The within- and between-topic distance ranges **overlap** on every sample.
#    No single global threshold separates topics perfectly with
#    all-MiniLM-L6-v2, so a choice about which way to fail is unavoidable.
#
# 2. The largest safe threshold **moves with the sample** (0.45 vs 0.55 here).
#    An earlier version of this constant was calibrated on `broad-11` alone,
#    picked 0.55, and then merged photosynthesis with mitochondria on the
#    sparser set. A single global constant is genuinely fragile; per-user or
#    per-document calibration is the real fix if this proves to matter.
#
# Given that, 0.45 is the value safe across all samples — the minimum of the
# per-sample maxima, not the maximum. The asymmetry is deliberate:
#
#   - Merging unrelated concepts actively corrupts knowledge tracing. It writes
#     wrong labels into the interaction log, and the scheduler then reviews the
#     wrong material.
#   - Over-splitting merely forgoes generalisation. Both concepts are still
#     tracked correctly; the model just needs more data per concept.
#
# Re-run the calibration against real Marigold cards once there are enough of
# them. This is the number most worth revisiting with data.
DEFAULT_DISTANCE_THRESHOLD = 0.45

DEFAULT_MODEL_NAME = "all-MiniLM-L6-v2"


@dataclass(frozen=True)
class ConceptCluster:
    """One discovered concept."""

    cluster_id: int
    label: str
    member_indices: List[int]
    centroid: np.ndarray

    @property
    def size(self) -> int:
        return len(self.member_indices)


def embed_texts(
    texts: Sequence[str], model_name: str = DEFAULT_MODEL_NAME
) -> np.ndarray:
    """Embed card texts with a pretrained sentence encoder.

    all-MiniLM-L6-v2 per the brief: 384 dimensions, ~80MB, and fast enough on
    CPU that the $20/month node can run it. No custom embedder is trained —
    there is no labelled data that would make one better, and the generic model
    already separates "photosynthesis" from "mitosis" perfectly well.

    Imported lazily so the rest of the pipeline — and its tests — do not require
    a ~2GB dependency tree to be installed.
    """
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(model_name)
    return np.asarray(
        model.encode(list(texts), normalize_embeddings=True, show_progress_bar=False),
        dtype=np.float32,
    )


def cluster_embeddings(
    embeddings: np.ndarray,
    distance_threshold: float = DEFAULT_DISTANCE_THRESHOLD,
) -> np.ndarray:
    """Assign each embedding a cluster id. Returns int array of shape (n,).

    Every point receives a real cluster id; there is no noise label.
    """
    n = embeddings.shape[0]
    if n == 0:
        return np.zeros(0, dtype=np.int64)
    if n == 1:
        return np.zeros(1, dtype=np.int64)

    from sklearn.cluster import AgglomerativeClustering

    clusterer = AgglomerativeClustering(
        n_clusters=None,
        distance_threshold=distance_threshold,
        metric="cosine",
        # Average linkage: complete linkage is dominated by the single most
        # distant pair, which fragments legitimately broad concepts, while
        # single linkage chains unrelated cards together through intermediate
        # ones. Average is the stable middle for text embeddings.
        linkage="average",
    )
    return clusterer.fit_predict(embeddings).astype(np.int64)


def _label_cluster(texts: Sequence[str], members: Sequence[int], centroid: np.ndarray,
                   embeddings: np.ndarray) -> str:
    """Name a cluster by its most central member.

    The card closest to the centroid is the most representative one, which
    makes a far better human-readable label than concatenating keywords. This
    is a display label only — nothing keys off it.
    """
    if not members:
        return ""
    sims = embeddings[list(members)] @ centroid
    best = int(np.argmax(sims))
    text = texts[members[best]].strip()
    return text[:80] + ("..." if len(text) > 80 else "")


def cluster_flashcards(
    texts: Sequence[str],
    distance_threshold: float = DEFAULT_DISTANCE_THRESHOLD,
    embedder: Optional[Callable[[Sequence[str]], np.ndarray]] = None,
) -> List[ConceptCluster]:
    """Cluster flashcard texts into concepts.

    `embedder` is injectable so tests can supply deterministic vectors instead
    of downloading a model; production passes None and gets `embed_texts`.

    Clusters are returned in descending size order, and cluster ids are
    reassigned to be contiguous from 0 in that order, so the output does not
    depend on sklearn's internal numbering.
    """
    if not texts:
        return []

    encode = embedder or (lambda t: embed_texts(t))
    embeddings = encode(texts)

    if embeddings.shape[0] != len(texts):
        raise ValueError(
            f"embedder returned {embeddings.shape[0]} vectors for {len(texts)} texts"
        )

    raw_labels = cluster_embeddings(embeddings, distance_threshold)

    groups: Dict[int, List[int]] = {}
    for idx, label in enumerate(raw_labels):
        groups.setdefault(int(label), []).append(idx)

    # Largest first, ties broken by first member index for determinism.
    ordered = sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[1][0]))

    clusters: List[ConceptCluster] = []
    for new_id, (_, members) in enumerate(ordered):
        centroid = embeddings[members].mean(axis=0)
        norm = np.linalg.norm(centroid)
        if norm > 0:
            centroid = centroid / norm
        clusters.append(
            ConceptCluster(
                cluster_id=new_id,
                label=_label_cluster(texts, members, centroid, embeddings),
                member_indices=sorted(members),
                centroid=centroid.astype(np.float32),
            )
        )

    return clusters


def assign_concepts(
    card_ids: Sequence[str],
    texts: Sequence[str],
    distance_threshold: float = DEFAULT_DISTANCE_THRESHOLD,
    embedder: Optional[Callable[[Sequence[str]], np.ndarray]] = None,
) -> Dict[str, int]:
    """Map card id -> concept cluster id.

    The shape the backend needs when writing `flashcards.concept_id`.
    """
    if len(card_ids) != len(texts):
        raise ValueError(
            f"card_ids and texts must be the same length "
            f"({len(card_ids)} vs {len(texts)})"
        )

    clusters = cluster_flashcards(texts, distance_threshold, embedder)
    assignment: Dict[str, int] = {}
    for cluster in clusters:
        for idx in cluster.member_indices:
            assignment[card_ids[idx]] = cluster.cluster_id
    return assignment
