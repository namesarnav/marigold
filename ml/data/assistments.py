"""ASSISTments 2009 (skill builder) download and preprocessing.

Used only to validate the SAKT implementation before it touches real Marigold
data. Published reproductions of SAKT on this dataset land around AUC
0.72-0.75 (the original paper reports higher, but that number is widely
reported as difficult to reproduce), so that band is the sanity target.

## Source and its ordering caveat

The canonical `skill_builder_data_corrected.csv` is distributed through the
ASSISTments site rather than a stable public URL, so this pulls a widely-used
research mirror instead.

**The mirror's `timestamp` column is entirely zero.** Verified on download:
every one of the 278,336 rows carries timestamp 0. There is therefore no
wall-clock information in this dataset at all, and any "temporal" split must
use *row order* as the interaction order.

That is the standard interpretation for this benchmark — the file preserves the
original per-student log order — but it is an assumption, not something the data
proves, so it is stated here rather than buried. `load_interactions` returns an
explicit `order` array so the split function never has to guess what ordering
means, and for real Marigold data that array carries actual timestamps.

The practical consequence: this benchmark validates the *sequence* modelling and
the split logic. It cannot validate anything time-dependent, which is why the
forgetting decay in `ml/inference/predict.py` is a separate, separately-tested
component rather than something the benchmark signs off on.
"""

from __future__ import annotations

import urllib.request
from pathlib import Path
from typing import Tuple

import numpy as np
import pandas as pd

from ml.config import DATA_DIR

# Research mirror from theophilee/learner-performance-prediction. Tab-separated,
# columns: user_id, item_id, timestamp, correct, skill_id.
ASSISTMENTS_2009_URL = (
    "https://raw.githubusercontent.com/theophilee/learner-performance-prediction"
    "/master/data/assistments09/preprocessed_data.csv"
)

# Guards against a silently truncated download or a mirror swapping contents.
EXPECTED_ROWS = 278_336
EXPECTED_STUDENTS = 3_114


def download(dest_dir: Path = DATA_DIR, force: bool = False) -> Path:
    """Fetch the dataset, skipping the download if it is already present."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    path = dest_dir / "assistments09.csv"

    if path.exists() and not force:
        return path

    print(f"Downloading ASSISTments 2009 -> {path}")
    urllib.request.urlretrieve(ASSISTMENTS_2009_URL, path)
    print(f"Downloaded {path.stat().st_size:,} bytes")
    return path


def load_interactions(
    path: Path | None = None, verify: bool = True
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, int]:
    """Load and clean the interaction table.

    Returns `(student_ids, skills, correct, order, n_skills)`.

    Skills are remapped to a contiguous 0-based range so they can index an
    embedding table directly. `order` is the per-student row index, for the
    reason documented in this module's docstring.
    """
    if path is None:
        path = download()

    frame = pd.read_csv(path, sep="\t")

    required = {"user_id", "skill_id", "correct"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"{path} is missing expected columns: {sorted(missing)}")

    if verify:
        _verify_source(frame)

    # Rows without a skill cannot be used: the model indexes an embedding by
    # skill, and imputing one would invent training signal.
    frame = frame.dropna(subset=["skill_id", "correct", "user_id"])

    # `correct` must be binary. The corrected dataset occasionally carries other
    # values from partial-credit items; those are not binary outcomes and are
    # dropped rather than rounded into one.
    frame = frame[frame["correct"].isin([0, 1])]

    # Preserve file order within each student, then group. `kind="stable"`
    # matters: it is what makes row order the tiebreak.
    frame = frame.reset_index(drop=True)
    frame["_row"] = np.arange(len(frame), dtype=np.int64)
    frame = frame.sort_values(["user_id", "_row"], kind="stable")

    # Per-student sequential position. This is the `order` key — see the module
    # docstring on why it is not the timestamp column.
    frame["_order"] = frame.groupby("user_id").cumcount()

    skill_codes, _ = pd.factorize(frame["skill_id"], sort=True)
    n_skills = int(skill_codes.max()) + 1

    return (
        frame["user_id"].to_numpy(dtype=np.int64),
        skill_codes.astype(np.int64),
        frame["correct"].to_numpy(dtype=np.int8),
        frame["_order"].to_numpy(dtype=np.int64),
        n_skills,
    )


def _verify_source(frame: pd.DataFrame) -> None:
    """Warn loudly if the mirror no longer matches what was validated against."""
    n_rows = len(frame)
    n_students = frame["user_id"].nunique()

    if n_rows != EXPECTED_ROWS or n_students != EXPECTED_STUDENTS:
        print(
            "WARNING: dataset does not match the validated snapshot "
            f"(rows {n_rows:,} vs {EXPECTED_ROWS:,}, "
            f"students {n_students:,} vs {EXPECTED_STUDENTS:,}). "
            "The mirror may have changed; AUC is not comparable to the "
            "recorded baseline."
        )

    if "timestamp" in frame.columns:
        n_nonzero = int((frame["timestamp"] != 0).sum())
        if n_nonzero == 0:
            # Expected for this mirror. Printed so the caveat is visible in the
            # training log rather than only in a docstring.
            print(
                "NOTE: all timestamps are zero in this mirror — "
                "interaction order is row order (see module docstring)."
            )
