# ml/ — knowledge tracing and concept clustering

SAKT-based knowledge tracing for Marigold: predicts P(correct) for a user on a
concept at a point in time, and ranks concepts by forgetting risk.

> Note: the repo's root `.gitignore` contains a `*md` rule, so this file is not
> tracked by git. The load-bearing reasoning is duplicated in module docstrings
> and comments, which are.

## Headline result

**Held-out AUC on ASSISTments 2009: `0.7535`**

| | |
| --- | --- |
| Students | 3,022 (after dropping those too short to split) |
| Train interactions | 250,502 |
| Held-out interactions scored | 27,218 |
| Best epoch | 10 of 15 (early-stopped, patience 5) |
| Model size | 215,681 parameters |
| Training time | ~35s total on Apple MPS |

Reruns land at 0.7535 / 0.7536 — the pipeline is seeded, but MPS float
reduction order makes the last digit nondeterministic.

That sits at the top of the 0.70–0.75 band you specified, which is the range
published SAKT *reproductions* land in on this dataset (the original paper
reports higher and is widely noted as hard to reproduce). Being **inside** the
band rather than above it is the reassuring direction — an AUC of 0.85+ here
would be the signature of label leakage.

Reproduce:

```bash
pip install -r ml/requirements.txt
python -m ml.training.train_sakt              # full run
python -m ml.training.train_sakt --epochs 2 --limit-students 300   # fast smoke
```

The script prints an explicit verdict on the AUC it obtained, including naming
leakage as the likely cause if the number comes back implausibly high.

## Leakage: what prevents it, and how that is verified

You flagged this as the highest-risk area. There are two independent failure
modes and each has its own guard.

**1. Split leakage — a student's held-out interactions appearing in training.**

`ml/data/splits.py` is a pure, isolated module. Per student: sort by an explicit
`order` key, hold out the most recent N, train on everything earlier. Verified by:

- `assert_no_leakage()` runs inside every training job, before a single gradient
  step, and reconstructs each student's history from its two halves to prove
  nothing was duplicated or dropped.
- `test_splits.py` (22 tests) asserts held-out interactions are exactly the tail,
  that the split is deterministic and independent of global RNG state, and — via
  `test_assert_no_leakage_catches_a_corrupted_boundary` — that the guard itself
  actually fires when handed a deliberately leaked split.

**2. Framing leakage — the answer being predicted visible in the model's input.**

Two mechanisms, both required:

- A one-step offset: `past_interactions[i]` encodes step *i*, while the query and
  target are step *i+1*. A position's own answer is never in its own input.
- A causal mask: strictly upper-triangular, so position *i* attends only to key
  positions ≤ *i*. Note the diagonal is *allowed* — key *i* is the interaction at
  step *i*, which precedes query *i*.

Verified by:

- `positional_sanity_check()` runs in every training job: it perturbs inputs
  *after* a position and requires that position's prediction to be unchanged.
- `test_sanity_check_fires_when_the_mask_is_disabled` replaces the mask with an
  all-permissive one and asserts the check fails, so the guard is not decoration.
- `test_random_labels_yield_chance_auc` trains on pure coin-flip labels and
  requires AUC to stay near 0.5. If any part of the framing exposed a target,
  the model could fit noise and this would rise sharply. This is the strongest
  end-to-end evidence available.

## Judgment calls

Every nontrivial choice lives in `ml/config.py` with its reasoning. The ones
worth your attention:

| Choice | Value | Why |
| --- | --- | --- |
| Sequence length cap | 200 | Attention is O(L²); the median ASSISTments student is well under 200. Longer histories are **chunked, not truncated**, so no interaction is discarded. |
| Embedding dim | 128 | Paper sweeps 50–200. Keeps the model ~1M params, which matters on a CPU-only t4g sharing 2GB with Postgres. |
| Attention heads | 8 | 16 dims/head. Trades head width for more distinct attention patterns, suited to a many-skill setting. |
| Holdout size | Fixed N=10 | A *fraction* would let the few students with 1000+ interactions dominate the AUC. Capped at 50% of history so short students aren't mostly-eval. |
| Cold-start threshold | 20 interactions | A round number, not a tuned one — flagged as such, and should be re-derived on real data. |
| Clustering algorithm | Agglomerative, not HDBSCAN | See below. |
| Distance threshold | 0.45 | Calibrated, and the calibration is a runnable script. See below. |

## Step 3 — cold start: population prior, not BKT

You offered either; **this implements the population-average per-concept
difficulty prior.** Reasoning:

BKT needs four parameters per concept fit by EM, and EM on BKT is notoriously
prone to converging on degenerate parameters (slip + guess > 1) that make
predictions get *worse* as a student answers more correctly. Detecting and
constraining that is more machinery than this path warrants — and subtle
wrongness in the fallback is especially bad, because the fallback is precisely
what a brand-new user experiences.

It also matches what cold start actually knows. Below ~20 interactions there is
not enough signal to identify a per-student learning trajectory, which is the
one thing BKT adds. What *is* available is "how hard is this concept generally,
nudged by the little we've seen" — a Beta-Bernoulli posterior mean, which
behaves sanely at every sample size for free.

The **blending stretch goal is implemented**: `sakt_blend_weight` ramps linearly
from prior to SAKT over 20 interactions past the threshold, because a hard
switch would visibly reorder a user's review queue on a single answer. Setting
`blend_window = 0` gives the hard switch instead, and that path is tested too.

`should_use_sakt(user_interaction_count) -> bool` is a named, isolated,
separately-tested function as specified — never an inline comparison.

## Step 1 — clustering: agglomerative, and a real calibration

**Agglomerative with a cosine distance threshold, not HDBSCAN.** HDBSCAN labels
sparse points as noise (`-1`), and a card with no concept produces interactions
the tracer cannot attribute to anything. A one-off card is a legitimate
concept of size one, not noise. Agglomerative assigns every point, produces
singletons naturally, and its knob — "cards closer than this are the same
concept" — is directly interpretable, unlike `min_cluster_size`/`min_samples`.
Cost: O(n²) memory, irrelevant at a user's library size.

The threshold was calibrated rather than guessed, and **the calibration caught
its own mistake**. Run `python -m ml.concepts.calibrate`:

```
sample     within-topic distance         between-topic distance    largest pure
broad-11   min .265 mean .526 max .703   min .433 mean .851            0.55
sparse-7   min .265 mean .451 max .513   min .433 mean .774            0.45
```

Two findings, both material:

1. **The distributions overlap on every sample.** No global threshold separates
   topics perfectly with all-MiniLM-L6-v2, so a failure direction must be chosen.
2. **The safe threshold moves with the sample.** An earlier version calibrated
   on `broad-11` alone, picked 0.55, and then merged photosynthesis with
   mitochondria on the sparser set. The script now evaluates multiple samples
   and reports the value safe across all of them.

Default is **0.45** — the *minimum* of the per-sample maxima. The asymmetry is
deliberate: merging unrelated concepts writes wrong labels into the interaction
log and sends the scheduler after the wrong material, while over-splitting only
forgoes generalisation. A single global constant is genuinely fragile here;
per-user calibration is the real fix if it matters. Re-run against real card
data.

## Step 4 — inference

```python
rank_concepts_by_forgetting_risk(user_id, candidate_concepts, as_of) -> list[tuple[str, float]]
```

Exactly the specified signature. It internally routes cold-start vs. SAKT,
loads artifacts once, and returns concepts ascending by P(correct).

`as_of` is a real input, not a placeholder: it computes elapsed time since each
concept was last practised, and is **not clamped to now**, so passing a future
date returns a projected P(correct). That is the exam-readiness hook, live and
tested — the feature around it (scheduling simulation, revision planning) is not
built, and the projection does not model reviews the user might do in between.

Two things worth knowing:

- **History is loaded through an injected `history_provider`**, and the function
  **raises `HistoryUnavailable`** rather than ranking on an empty history if none
  is configured. Silently returning prior-only numbers for a user with months of
  data is a wrong answer that looks completely right, which is the worst kind.
  The backend wires a real loader at startup; tests pass history explicitly.
- **A missing checkpoint is not an error.** Every user falls back to the prior.
  That is exactly Marigold's state before the first model trains on real data,
  and the service must serve in it rather than crash-loop.

### The time-decay heuristic — read this before trusting it

Vanilla SAKT is **order-based**: it knows what order a user answered things in,
not how long ago. Marigold's premise is time-dependent forgetting. So an
exponential decay toward a floor is applied *on top of* the model output:

```
p(t) = floor + (p0 - floor) * 2 ** (-t / half_life)
```

This is a **documented heuristic with a fixed 7-day half-life, not a learned or
fitted component.** It is kept separate and separately tested so it can be
swapped. The principled version is a time-aware architecture — AKT's monotonic
attention, or a Hawkes-process KT — which is a later slice. Decay is toward a
0.25 floor rather than zero because a four-option quiz can be guessed; decaying
to zero would rank forgotten material as more urgent than *never-seen* material,
which is backwards.

Note the resulting product behaviour, which is a design choice you may want to
revisit: a concept studied once and long forgotten ranks **above** a
never-studied concept. "Forgetting risk" strictly implies you must have learned
it first, but a review feed might reasonably want new material surfaced too.

## Step 5 — tests

**111 tests, all passing.** `cd ml && pytest` (add `-m "not slow"` to skip the
two that train a small model or download the encoder).

| File | Count | Covers |
| --- | --- | --- |
| `test_splits.py` | 22 | Temporal split: no leakage, determinism, tail-only holdout, tie stability, the guard firing |
| `test_sequences.py` | 16 | Input framing, one-step offset, causal mask, chunking, random-label AUC |
| `test_coldstart.py` | 27 | Threshold boundary, blend ramp monotonicity, prior shrinkage, serialisation |
| `test_predict.py` | 30 | Ranking order, tie-breaking, cold-start routing, SAKT path, decay, history provider |
| `test_cluster.py` | 16 | No noise labels, singletons, determinism, contiguous ids, real encoder |

## Data caveat you should know about

**The ASSISTments mirror's `timestamp` column is entirely zero** — all 278,336
rows. There is no wall-clock information in it whatsoever, so "temporal" split
means *row order*, which is the standard interpretation for this benchmark but
is an assumption, not something the data proves. It is stated in
`ml/data/assistments.py` and printed at every training run rather than buried.

The consequence: this benchmark validates the **sequence** modelling and the
split logic. It cannot validate anything time-dependent, which is exactly why
the forgetting decay is a separate component with its own tests rather than
something the AUC number signs off on.

The canonical `skill_builder_data_corrected.csv` (which has a real `order_id`)
is distributed via the ASSISTments site rather than a stable public URL; several
research mirrors were probed and returned 404.

## Schema — and an overlap that needs a decision

`ml/schema.py` holds the DB-agnostic SQLAlchemy models. **It overlaps with
`backend/models.py`, which already has `concepts` and `interactions` in use**,
and the shapes differ (`cluster_label` vs `label`, `card_id` vs `flashcard_id`,
`timestamp` vs `responded_at`, plus `source_card_ids`). The full mapping table
is in that module's docstring. This is written as the *target* schema with the
divergence recorded, rather than silently creating a second conflicting
definition — reconciling them is a migration and needs a decision.

Two divergences are substantive, not cosmetic:

- **`correct` is nullable.** The backend is right and this follows it: `NULL`
  means *skipped*. Storing a skip as `False` would teach the model that running
  out of time means forgetting. Skips are filtered before reaching the model in
  both `predict.py` and `coldstart.py`, and that is tested.
- **`source_card_ids` denormalises** a relationship the backend already derives
  from `flashcards.concept_id`. Included as specified, but it is a derived
  cache, not authority.

For Postgres, `embedding` should become pgvector's `vector(384)`. That needs the
extension installed on the in-cluster Postgres — a real migration, not a column
type swap.

## Not built yet

- **No FastAPI service.** `ml/` is a library; nothing is exposed over HTTP. The
  serving deps are pinned in `requirements.txt` but unused.
- **No Marigold-trained model.** The checkpoint is ASSISTments-only. Marigold's
  own concepts need `concept_to_skill` populated and a training run on real
  interaction data; until then every user takes the prior path, correctly.
- **No training-data export** from the backend's `/api/interactions/me` into the
  training pipeline.
- **No Dockerfile** for the ML image, and no spot-instance training Terraform.
- **Cold-start threshold is unvalidated** on real data — 20 is a reasoned guess.
