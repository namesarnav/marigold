"""Turning split student histories into padded SAKT training windows.

## The framing, and why it cannot leak

SAKT predicts step t from the interactions that came strictly before it. Each
window of L+1 consecutive steps produces:

    past_interactions[i] = encode(skill[i],   correct[i])     for i in 0..L-1
    query_skills[i]      = skill[i+1]                          for i in 0..L-1
    targets[i]           = correct[i+1]                        for i in 0..L-1

So the tensor the model sees as keys/values is offset one step behind the
tensor it sees as queries. The label for a position is never encoded into any
input at that position: `correct[i+1]` appears in `past_interactions` only at
index i+1, which the causal mask makes invisible when predicting index i.

Two distinct guards, both necessary:

1. The one-step offset above, which keeps the *current* answer out of the input.
2. The causal mask in the model, which keeps *future* answers out.

Dropping either one produces a model that scores ~0.99 AUC, which is the
classic tell for this bug.

## Eval windows

A held-out interaction is scored using the student's earlier interactions as
context. That is realistic — at serving time a user's past is known — and is
not leakage, because context is always drawn from strictly earlier positions.
`score_mask` marks which positions count toward the metric, so context
positions contribute to attention but never to AUC.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence

import numpy as np
import torch
from torch.utils.data import DataLoader, Dataset

from ml.config import SAKT, SAKTConfig
from ml.data.splits import TemporalSplit

# 0 is reserved for padding in both the skill and interaction embedding tables,
# so real ids start at 1.
PAD_ID = 0


def encode_interaction(skill: np.ndarray, correct: np.ndarray, n_skills: int) -> np.ndarray:
    """Encode a (skill, correctness) pair as a single embedding index.

    Layout, with 0 reserved for padding:
        incorrect on skill s -> 1 + s
        correct   on skill s -> 1 + n_skills + s

    A single joint embedding, rather than summing separate skill and
    correctness embeddings, is what the SAKT paper specifies: it lets the model
    learn a distinct representation for getting a specific skill wrong versus
    right, which is the signal knowledge tracing runs on.
    """
    return (1 + skill + correct.astype(np.int64) * n_skills).astype(np.int64)


@dataclass
class Window:
    """One fixed-length training or evaluation window."""

    past_interactions: np.ndarray  # (L,) embedding ids, 0 = pad
    query_skills: np.ndarray  # (L,) skill ids + 1, 0 = pad
    targets: np.ndarray  # (L,) 0/1, undefined where score_mask == 0
    score_mask: np.ndarray  # (L,) 1 where the position counts


def _pack(
    skills: np.ndarray,
    correct: np.ndarray,
    n_skills: int,
    max_len: int,
    score_from: int = 0,
) -> List[Window]:
    """Build windows from one contiguous run of steps.

    `score_from` is an index into `skills`: positions before it provide context
    only. Windows are cut so that every scored step appears as a query.
    """
    n = len(skills)
    if n < 2:
        # A single step can never be predicted: there is nothing before it.
        return []

    interactions = encode_interaction(skills, correct, n_skills)
    queries = (skills + 1).astype(np.int64)

    windows: List[Window] = []
    # Step over the sequence in chunks of `max_len` predictions. Each chunk
    # predicts steps [start+1, start+max_len], conditioned on step start onward.
    start = 0
    while start < n - 1:
        end = min(start + max_len, n - 1)  # last predicted index is `end`
        length = end - start

        past = interactions[start:end]
        query = queries[start + 1 : end + 1]
        target = correct[start + 1 : end + 1].astype(np.int64)

        # A position is scored when the step being predicted is at or after
        # score_from.
        predicted_idx = np.arange(start + 1, end + 1)
        mask = (predicted_idx >= score_from).astype(np.int64)

        pad = max_len - length
        if pad > 0:
            past = np.concatenate([past, np.full(pad, PAD_ID, dtype=np.int64)])
            query = np.concatenate([query, np.full(pad, PAD_ID, dtype=np.int64)])
            target = np.concatenate([target, np.zeros(pad, dtype=np.int64)])
            mask = np.concatenate([mask, np.zeros(pad, dtype=np.int64)])

        if mask.sum() > 0:
            windows.append(Window(past, query, target, mask))

        start = end

    return windows


def build_train_windows(
    splits: Sequence[TemporalSplit], n_skills: int, config: SAKTConfig = SAKT
) -> List[Window]:
    """Windows over each student's training portion only.

    Held-out interactions are not passed in at all, so they cannot appear in a
    training window even accidentally.
    """
    windows: List[Window] = []
    for split in splits:
        windows.extend(
            _pack(
                split.train_skills,
                split.train_correct,
                n_skills,
                config.max_seq_len,
                score_from=0,
            )
        )
    return windows


def build_eval_windows(
    splits: Sequence[TemporalSplit], n_skills: int, config: SAKTConfig = SAKT
) -> List[Window]:
    """Windows scoring only held-out interactions.

    Each window is the tail of the student's training history (as context)
    followed by their held-out interactions (scored). Context is capped so the
    window still fits `max_seq_len` predictions.
    """
    windows: List[Window] = []
    for split in splits:
        n_eval = len(split.eval_skills)
        if n_eval == 0:
            continue

        # Leave room for the eval steps; spend the rest on context. At least one
        # context step is required, since the first step of a window is never
        # predicted.
        context_budget = max(1, config.max_seq_len - n_eval)
        context_skills = split.train_skills[-context_budget:]
        context_correct = split.train_correct[-context_budget:]

        skills = np.concatenate([context_skills, split.eval_skills])
        correct = np.concatenate([context_correct, split.eval_correct])

        windows.extend(
            _pack(
                skills,
                correct,
                n_skills,
                config.max_seq_len,
                score_from=len(context_skills),
            )
        )
    return windows


class WindowDataset(Dataset):
    """Thin torch Dataset over prebuilt windows."""

    def __init__(self, windows: Sequence[Window]):
        self.windows = list(windows)

    def __len__(self) -> int:
        return len(self.windows)

    def __getitem__(self, idx: int):
        w = self.windows[idx]
        return (
            torch.from_numpy(w.past_interactions),
            torch.from_numpy(w.query_skills),
            torch.from_numpy(w.targets).float(),
            torch.from_numpy(w.score_mask).bool(),
        )


def make_loader(
    windows: Sequence[Window],
    batch_size: int,
    shuffle: bool,
    generator: torch.Generator | None = None,
) -> DataLoader:
    return DataLoader(
        WindowDataset(windows),
        batch_size=batch_size,
        shuffle=shuffle,
        generator=generator,
        drop_last=False,
    )
