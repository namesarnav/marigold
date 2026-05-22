"""Calibrate the clustering distance threshold against labelled card text.

Run:
    python -m ml.concepts.calibrate

Reproduces the numbers quoted above `DEFAULT_DISTANCE_THRESHOLD` in
`ml/concepts/cluster.py`. Exists so that constant is a measurement anyone can
re-derive, not folklore in a comment.

Calibrating on a single sample is not enough, and this script is built around
that lesson. An earlier version measured one 11-card set, concluded 0.55 was
safe, and that threshold then merged two unrelated topics on a *different*
7-card set drawn from the same subjects. The safe threshold moves with sample
size and composition, so the script evaluates several labelled samples and
reports the value that is safe across **all** of them.

The samples are still small and hand-written, which bounds how much they can
say. Point `--cards` at a CSV export of real Marigold flashcards (`topic,text`)
once there is one — that is the measurement that should govern the constant.
"""

from __future__ import annotations

import argparse
import itertools
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

import numpy as np

from ml.concepts.cluster import cluster_embeddings, embed_texts

# (topic, card text) samples. Topics are the ground truth a good threshold
# should recover. Deliberately more than one sample, and of different sizes:
# see the module docstring on why a single sample misleads.
SAMPLES: Dict[str, List[Tuple[str, str]]] = {
    "broad-11": [
        ("photosynthesis", "What is photosynthesis?"),
        ("photosynthesis", "Which organelle performs photosynthesis?"),
        ("photosynthesis", "What does chlorophyll absorb?"),
        ("photosynthesis", "Explain the light-dependent reactions"),
        ("mitochondria", "What is the powerhouse of the cell?"),
        ("mitochondria", "How does the mitochondrion make ATP?"),
        ("mitochondria", "Where does cellular respiration occur?"),
        ("france", "What is the capital of France?"),
        ("france", "Which river runs through Paris?"),
        ("complexity", "What is the time complexity of binary search?"),
        ("complexity", "How fast does quicksort run on average?"),
    ],
    # Sparser, and with two topics that are genuinely adjacent (both cell
    # biology). This is the sample that breaks an over-eager threshold.
    "sparse-7": [
        ("photosynthesis", "What is photosynthesis?"),
        ("photosynthesis", "Which organelle performs photosynthesis?"),
        ("photosynthesis", "What does chlorophyll absorb?"),
        ("mitochondria", "What is the powerhouse of the cell?"),
        ("mitochondria", "How does the mitochondrion make ATP?"),
        ("france", "What is the capital of France?"),
        ("france", "Which river runs through Paris?"),
    ],
}

CANDIDATE_THRESHOLDS = [0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.85]


def load_cards(path: Path | None) -> Dict[str, List[Tuple[str, str]]]:
    if path is None:
        return SAMPLES

    import csv

    rows: List[Tuple[str, str]] = []
    with open(path, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            topic = (row.get("topic") or "").strip()
            text = (row.get("text") or "").strip()
            if topic and text:
                rows.append((topic, text))
    if not rows:
        raise ValueError(f"{path} produced no usable rows (need topic,text columns)")
    return {path.stem: rows}


def distance_distributions(
    embeddings: np.ndarray, labels: Sequence[str]
) -> Tuple[np.ndarray, np.ndarray]:
    """Cosine distances split into within-topic and between-topic pairs."""
    distances = 1.0 - embeddings @ embeddings.T
    within, between = [], []
    for i, j in itertools.combinations(range(len(labels)), 2):
        (within if labels[i] == labels[j] else between).append(distances[i, j])
    return np.array(within), np.array(between)


def cluster_purity(labels: Sequence[str], assignments: np.ndarray) -> bool:
    """True when no cluster mixes two different ground-truth topics."""
    return all(
        len({labels[i] for i in range(len(labels)) if assignments[i] == cluster}) == 1
        for cluster in set(assignments.tolist())
    )


def evaluate_sample(
    name: str, cards: Sequence[Tuple[str, str]]
) -> Tuple[float | None, int]:
    """Print one sample's distance profile and return its largest pure threshold."""
    labels = [topic for topic, _ in cards]
    texts = [text for _, text in cards]
    n_topics = len(set(labels))

    print(f"\n--- sample '{name}': {len(cards)} cards, {n_topics} topics ---")
    embeddings = embed_texts(texts)

    within, between = distance_distributions(embeddings, labels)
    print(
        f"  within-topic  cosine distance: "
        f"min {within.min():.3f}  mean {within.mean():.3f}  max {within.max():.3f}"
    )
    print(
        f"  between-topic cosine distance: "
        f"min {between.min():.3f}  mean {between.mean():.3f}  max {between.max():.3f}"
    )
    if within.max() > between.min():
        print("  distributions OVERLAP: no threshold separates these topics perfectly")

    results = []
    for threshold in CANDIDATE_THRESHOLDS:
        assignments = cluster_embeddings(embeddings, distance_threshold=threshold)
        results.append(
            (
                threshold,
                len(set(assignments.tolist())),
                cluster_purity(labels, assignments),
            )
        )

    pure = [t for t, _, is_pure in results if is_pure]
    best = max(pure) if pure else None

    print("  threshold   clusters   pure")
    for threshold, n_clusters, is_pure in results:
        marker = "  <- largest pure" if threshold == best else ""
        print(f"    {threshold:.2f}       {n_clusters:3d}      {str(is_pure):5s}{marker}")

    return best, n_topics


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cards",
        type=Path,
        default=None,
        help="CSV with topic,text columns. Defaults to the built-in samples.",
    )
    args = parser.parse_args()

    samples = load_cards(args.cards)

    per_sample: Dict[str, float | None] = {}
    for name, cards in samples.items():
        best, _ = evaluate_sample(name, cards)
        per_sample[name] = best

    print("\n=== recommendation ===")
    for name, best in per_sample.items():
        shown = f"{best:.2f}" if best is not None else "none"
        print(f"  largest topic-pure threshold on '{name}': {shown}")

    usable = [b for b in per_sample.values() if b is not None]
    if not usable:
        print("\nNo candidate threshold kept clusters pure on any sample.")
        return

    safe = min(usable)
    print(
        f"\n  safe across all samples: {safe:.2f}"
        "\n  (the minimum, not the maximum: a threshold that merges unrelated"
        "\n   topics on any sample is unsafe, because a merge puts wrong labels"
        "\n   in the interaction log while an over-split only costs generalisation)"
    )
    if len(set(usable)) > 1:
        print(
            f"\n  NOTE: the safe threshold varies by sample "
            f"({min(usable):.2f}-{max(usable):.2f}). A single global constant is "
            "\n  fragile; re-run against real card data before trusting it."
        )


if __name__ == "__main__":
    main()
