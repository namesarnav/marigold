"""Train SAKT on ASSISTments 2009 and report held-out AUC.

Run:
    python -m ml.training.train_sakt
    python -m ml.training.train_sakt --epochs 3 --device cpu

The point of this script is validation, not production training: it exists to
show the SAKT implementation reaches published-reproduction AUC (~0.72-0.75) on
a public benchmark before the same code is pointed at Marigold users.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import torch
import torch.nn as nn
from sklearn.metrics import roc_auc_score

from ml.config import ARTIFACTS_DIR, SAKT, SPLIT, SAKTConfig
from ml.data.assistments import load_interactions
from ml.data.sequences import (
    build_eval_windows,
    build_train_windows,
    make_loader,
)
from ml.data.splits import (
    assert_no_leakage,
    group_interactions_by_student,
    split_all_students,
    split_summary,
)
from ml.models.sakt import SAKTModel, positional_sanity_check


def resolve_device(requested: str) -> torch.device:
    if requested != "auto":
        return torch.device(requested)
    if torch.cuda.is_available():
        return torch.device("cuda")
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def evaluate(
    model: SAKTModel, loader, device: torch.device
) -> Tuple[float, float, int]:
    """Return (auc, mean_bce, n_scored) over masked positions only."""
    model.eval()
    criterion = nn.BCEWithLogitsLoss(reduction="sum")

    all_probs: List[np.ndarray] = []
    all_targets: List[np.ndarray] = []
    total_loss = 0.0
    total_scored = 0

    with torch.no_grad():
        for past, query, target, mask in loader:
            past, query = past.to(device), query.to(device)
            target, mask = target.to(device), mask.to(device)

            logits = model(past, query)

            # Only masked positions contribute. Padding and, for eval windows,
            # context positions are excluded from both loss and AUC.
            selected_logits = logits[mask]
            selected_targets = target[mask]
            if selected_targets.numel() == 0:
                continue

            total_loss += criterion(selected_logits, selected_targets).item()
            total_scored += selected_targets.numel()

            all_probs.append(torch.sigmoid(selected_logits).float().cpu().numpy())
            all_targets.append(selected_targets.float().cpu().numpy())

    if not all_probs:
        return float("nan"), float("nan"), 0

    probs = np.concatenate(all_probs)
    targets = np.concatenate(all_targets)

    # AUC is undefined with a single class present.
    if len(np.unique(targets)) < 2:
        auc = float("nan")
    else:
        auc = float(roc_auc_score(targets, probs))

    return auc, total_loss / total_scored, total_scored


def train(
    epochs: int | None = None,
    device_str: str = "auto",
    config: SAKTConfig = SAKT,
    limit_students: int | None = None,
) -> Dict:
    device = resolve_device(device_str)
    torch.manual_seed(config.seed)
    np.random.seed(config.seed)

    print(f"device: {device}")
    print("Loading ASSISTments 2009...")
    student_ids, skills, correct, order, n_skills = load_interactions()
    print(
        f"  {len(student_ids):,} interactions | "
        f"{len(np.unique(student_ids)):,} students | {n_skills} skills | "
        f"{correct.mean():.3f} correct rate"
    )

    sequences = group_interactions_by_student(student_ids, skills, correct, order)
    if limit_students is not None:
        sequences = sequences[:limit_students]

    splits = split_all_students(sequences, SPLIT)

    # Verify the split invariants before spending any time training. A leak
    # discovered here costs seconds; discovered via a suspicious AUC it costs a
    # day of doubting the architecture.
    assert_no_leakage(sequences, splits)
    summary = split_summary(splits)
    print(
        f"  split: {summary['students']:,} students | "
        f"train {summary['train_interactions']:,} | "
        f"eval {summary['eval_interactions']:,} | "
        f"mean train len {summary['mean_train_len']:.1f} | "
        f"eval positive rate {summary['eval_positive_rate']:.3f}"
    )

    train_windows = build_train_windows(splits, n_skills, config)
    eval_windows = build_eval_windows(splits, n_skills, config)
    print(f"  windows: {len(train_windows):,} train | {len(eval_windows):,} eval")

    generator = torch.Generator().manual_seed(config.seed)
    train_loader = make_loader(
        train_windows, config.batch_size, shuffle=True, generator=generator
    )
    eval_loader = make_loader(eval_windows, config.batch_size, shuffle=False)

    model = SAKTModel(n_skills, config).to(device)
    print(f"  model: {model.n_parameters():,} trainable parameters")

    # Fail fast if the causal mask is wrong.
    positional_sanity_check(model)
    print("  causal-mask sanity check passed")

    optimizer = torch.optim.Adam(
        model.parameters(), lr=config.lr, weight_decay=config.weight_decay
    )
    criterion = nn.BCEWithLogitsLoss()

    n_epochs = epochs if epochs is not None else config.max_epochs
    best_auc = -1.0
    best_epoch = -1
    best_state = None
    history: List[Dict] = []
    epochs_without_improvement = 0

    for epoch in range(1, n_epochs + 1):
        model.train()
        started = time.time()
        running_loss = 0.0
        running_n = 0

        for past, query, target, mask in train_loader:
            past, query = past.to(device), query.to(device)
            target, mask = target.to(device), mask.to(device)

            logits = model(past, query)
            selected_logits = logits[mask]
            selected_targets = target[mask]
            if selected_targets.numel() == 0:
                continue

            loss = criterion(selected_logits, selected_targets)

            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), config.grad_clip)
            optimizer.step()

            running_loss += loss.item() * selected_targets.numel()
            running_n += selected_targets.numel()

        train_loss = running_loss / max(running_n, 1)
        auc, eval_loss, n_scored = evaluate(model, eval_loader, device)
        elapsed = time.time() - started

        history.append(
            {
                "epoch": epoch,
                "train_loss": train_loss,
                "eval_loss": eval_loss,
                "eval_auc": auc,
                "seconds": elapsed,
            }
        )
        print(
            f"epoch {epoch:3d} | train loss {train_loss:.4f} | "
            f"eval loss {eval_loss:.4f} | eval AUC {auc:.4f} | "
            f"{n_scored:,} scored | {elapsed:.1f}s"
        )

        if auc > best_auc:
            best_auc = auc
            best_epoch = epoch
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
            epochs_without_improvement = 0
        else:
            epochs_without_improvement += 1
            if epochs_without_improvement >= config.early_stopping_patience:
                print(
                    f"early stopping: no AUC improvement in "
                    f"{config.early_stopping_patience} epochs"
                )
                break

    result = {
        "best_auc": best_auc,
        "best_epoch": best_epoch,
        "n_skills": n_skills,
        "history": history,
        "split": summary,
        "config": config.__dict__,
    }

    _report_verdict(best_auc)

    if best_state is not None:
        ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
        checkpoint = ARTIFACTS_DIR / "sakt_assistments09.pt"
        torch.save(
            {
                "state_dict": best_state,
                "n_skills": n_skills,
                "config": config.__dict__,
                "eval_auc": best_auc,
            },
            checkpoint,
        )
        (ARTIFACTS_DIR / "sakt_assistments09_metrics.json").write_text(
            json.dumps(result, indent=2)
        )
        print(f"saved checkpoint -> {checkpoint}")

    return result


def _report_verdict(auc: float) -> None:
    """State plainly whether the number is in the expected band."""
    print()
    print(f"=== held-out AUC: {auc:.4f} ===")
    if np.isnan(auc):
        print("VERDICT: no AUC computed — check that the eval set has both classes.")
    elif auc > 0.85:
        print(
            "VERDICT: SUSPICIOUSLY HIGH. Published SAKT reproductions on "
            "ASSISTments 2009 land near 0.72-0.75. An AUC this high almost "
            "always means label leakage — check the train/eval split boundary "
            "and that the queried skill's own correctness is not in the input "
            "sequence."
        )
    elif auc >= 0.70:
        print("VERDICT: in the expected 0.70-0.75 band for SAKT on this dataset.")
    elif auc >= 0.65:
        print(
            "VERDICT: slightly below the expected band. Plausible for a short "
            "run; worth more epochs before concluding anything."
        )
    else:
        print(
            "VERDICT: BELOW EXPECTATION. At 0.5 the model is not learning at "
            "all — check that targets are aligned with queries and that the "
            "mask is not eliminating every scored position."
        )
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--epochs", type=int, default=None)
    parser.add_argument("--device", type=str, default="auto")
    parser.add_argument(
        "--limit-students",
        type=int,
        default=None,
        help="Train on the first N students only, for a fast smoke run.",
    )
    args = parser.parse_args()

    train(
        epochs=args.epochs,
        device_str=args.device,
        limit_students=args.limit_students,
    )


if __name__ == "__main__":
    main()
