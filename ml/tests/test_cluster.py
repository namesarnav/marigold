"""Tests for concept clustering.

A deterministic stub embedder is injected so these run without downloading a
model and without depending on what a particular sentence encoder happens to
think is similar. One opt-in test exercises the real encoder.
"""

import numpy as np
import pytest

from ml.concepts.cluster import (
    assign_concepts,
    cluster_embeddings,
    cluster_flashcards,
)


def stub_embedder(groups):
    """Embed by group id: same group -> identical unit vector.

    Makes cluster membership exactly predictable, so the test asserts on the
    clustering logic rather than on embedding quality.
    """
    def embed(texts):
        dim = max(groups.values()) + 1
        vectors = np.zeros((len(texts), dim), dtype=np.float32)
        for i, text in enumerate(texts):
            vectors[i, groups[text]] = 1.0
        return vectors

    return embed


def test_identical_topics_collapse_into_one_concept():
    texts = ["photosynthesis a", "photosynthesis b", "mitosis a"]
    groups = {"photosynthesis a": 0, "photosynthesis b": 0, "mitosis a": 1}

    clusters = cluster_flashcards(texts, embedder=stub_embedder(groups))

    assert len(clusters) == 2
    # Largest cluster first.
    assert clusters[0].size == 2
    assert clusters[0].member_indices == [0, 1]
    assert clusters[1].member_indices == [2]


def test_every_card_is_assigned_no_noise_label():
    """The reason agglomerative was chosen over HDBSCAN: no card is dropped."""
    texts = [f"t{i}" for i in range(7)]
    # Six of one topic, one lone outlier that HDBSCAN would likely call noise.
    groups = {f"t{i}": 0 for i in range(6)}
    groups["t6"] = 1

    clusters = cluster_flashcards(texts, embedder=stub_embedder(groups))

    assigned = sorted(i for c in clusters for i in c.member_indices)
    assert assigned == list(range(7))
    assert all(c.cluster_id >= 0 for c in clusters)


def test_singleton_clusters_are_legitimate():
    texts = ["a", "b", "c"]
    groups = {"a": 0, "b": 1, "c": 2}

    clusters = cluster_flashcards(texts, embedder=stub_embedder(groups))

    assert len(clusters) == 3
    assert all(c.size == 1 for c in clusters)


def test_cluster_ids_are_contiguous_from_zero():
    texts = [f"t{i}" for i in range(6)]
    groups = {"t0": 0, "t1": 0, "t2": 1, "t3": 1, "t4": 2, "t5": 2}

    clusters = cluster_flashcards(texts, embedder=stub_embedder(groups))

    assert [c.cluster_id for c in clusters] == list(range(len(clusters)))


def test_clusters_are_ordered_by_descending_size():
    texts = [f"t{i}" for i in range(6)]
    groups = {"t0": 0, "t1": 1, "t2": 1, "t3": 2, "t4": 2, "t5": 2}

    clusters = cluster_flashcards(texts, embedder=stub_embedder(groups))

    sizes = [c.size for c in clusters]
    assert sizes == sorted(sizes, reverse=True)


def test_clustering_is_deterministic():
    texts = [f"t{i}" for i in range(8)]
    groups = {f"t{i}": i % 3 for i in range(8)}
    embed = stub_embedder(groups)

    first = cluster_flashcards(texts, embedder=embed)
    second = cluster_flashcards(texts, embedder=embed)

    assert [c.member_indices for c in first] == [c.member_indices for c in second]
    assert [c.cluster_id for c in first] == [c.cluster_id for c in second]


def test_centroids_are_unit_norm():
    texts = ["a", "b", "c"]
    groups = {"a": 0, "b": 0, "c": 1}

    clusters = cluster_flashcards(texts, embedder=stub_embedder(groups))

    for cluster in clusters:
        assert np.linalg.norm(cluster.centroid) == pytest.approx(1.0, abs=1e-5)


def test_labels_come_from_a_member_card():
    texts = ["What is photosynthesis?", "Define photosynthesis", "What is mitosis?"]
    groups = {texts[0]: 0, texts[1]: 0, texts[2]: 1}

    clusters = cluster_flashcards(texts, embedder=stub_embedder(groups))

    for cluster in clusters:
        member_texts = [texts[i] for i in cluster.member_indices]
        assert any(cluster.label.startswith(t[:20]) for t in member_texts)


def test_empty_input_returns_no_clusters():
    assert cluster_flashcards([], embedder=stub_embedder({})) == []


def test_single_card_returns_one_cluster():
    clusters = cluster_flashcards(["only"], embedder=stub_embedder({"only": 0}))
    assert len(clusters) == 1
    assert clusters[0].member_indices == [0]


def test_cluster_embeddings_handles_degenerate_sizes():
    assert cluster_embeddings(np.zeros((0, 4), dtype=np.float32)).tolist() == []
    assert cluster_embeddings(np.ones((1, 4), dtype=np.float32)).tolist() == [0]


def test_threshold_controls_granularity():
    """A larger distance threshold merges more aggressively."""
    rng = np.random.default_rng(0)
    embeddings = rng.normal(size=(20, 8)).astype(np.float32)
    embeddings /= np.linalg.norm(embeddings, axis=1, keepdims=True)

    fine = len(np.unique(cluster_embeddings(embeddings, distance_threshold=0.1)))
    coarse = len(np.unique(cluster_embeddings(embeddings, distance_threshold=1.5)))

    assert fine >= coarse


# --- the backend-facing mapping ------------------------------------------

def test_assign_concepts_maps_every_card_id():
    card_ids = ["c1", "c2", "c3"]
    texts = ["a", "b", "c"]
    groups = {"a": 0, "b": 0, "c": 1}

    assignment = assign_concepts(card_ids, texts, embedder=stub_embedder(groups))

    assert set(assignment) == set(card_ids)
    assert assignment["c1"] == assignment["c2"]
    assert assignment["c3"] != assignment["c1"]


def test_assign_concepts_rejects_mismatched_lengths():
    with pytest.raises(ValueError, match="same length"):
        assign_concepts(["c1"], ["a", "b"], embedder=stub_embedder({"a": 0, "b": 0}))


def test_cluster_flashcards_rejects_a_bad_embedder():
    with pytest.raises(ValueError, match="vectors for"):
        cluster_flashcards(
            ["a", "b"], embedder=lambda t: np.zeros((1, 4), dtype=np.float32)
        )


# --- opt-in: the real encoder --------------------------------------------

@pytest.mark.slow
def test_real_embedder_separates_distinct_subjects():
    """Uses the actual all-MiniLM-L6-v2 model; downloads on first run."""
    st = pytest.importorskip("sentence_transformers")

    texts = [
        "What is photosynthesis?",
        "How do plants convert sunlight into energy?",
        "Which organelle carries out photosynthesis?",
        "What is the capital of France?",
        "Which city is France's capital?",
    ]

    clusters = cluster_flashcards(texts)
    assignment = {i: c.cluster_id for c in clusters for i in c.member_indices}

    # The three photosynthesis cards should not be split across three concepts,
    # and the France cards must not join them.
    assert assignment[3] == assignment[4]
    assert assignment[0] != assignment[3]
