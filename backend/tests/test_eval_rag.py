"""scripts/eval_rag.py: metric helpers, label validation, and a full dry run on
fakes — checking that what cannot be measured comes out null with a reason."""

import json

import pytest

from backend import gemini, usage
from backend.usage import CallRecord
from conftest import _TestSession
from fakes import FakeGemini
from scripts import eval_rag
from test_generation import TOPIC_TEXT, _pdf


# --- helpers --------------------------------------------------------------------


def test_nearest_rank_percentiles():
    assert eval_rag.nearest_rank_percentile([], 0.5) is None
    assert eval_rag.nearest_rank_percentile([3.0], 0.95) == 3.0
    values = list(range(1, 21))  # 1..20
    assert eval_rag.nearest_rank_percentile(values, 0.50) == 10
    assert eval_rag.nearest_rank_percentile(values, 0.95) == 19


def test_small_samples_flag_p95():
    summary = eval_rag.latency_summary([1.0, 2.0, 3.0])
    assert summary["n"] == 3
    assert summary["p95_seconds"]["value"] == 3.0
    assert "maximum" in summary["p95_seconds"]["note"]
    assert eval_rag.latency_summary([])["p50_seconds"]["value"] is None


def test_page_hit():
    assert eval_rag.page_hit([(3, 4)], [4])
    assert not eval_rag.page_hit([(1, 2), (5, 6)], [3, 4])


def _gen(prompt, output, thinking=None):
    return CallRecord(kind="generate", model="m", latency_seconds=1, prompt_tokens=prompt,
                      output_tokens=output, thinking_tokens=thinking)


def test_usage_totals_sum_api_counts_and_keep_estimates_apart():
    calls = [_gen(100, 20, 5), _gen(50, 10),
             CallRecord(kind="embed", model="e", latency_seconds=1, estimated_input_tokens=400)]
    totals = eval_rag.usage_totals(calls)
    assert totals["prompt_tokens"]["value"] == 150
    assert totals["output_tokens"]["value"] == 30
    assert totals["thinking_tokens"]["value"] == 5
    assert "counted as 0" in totals["thinking_tokens"]["note"]
    assert totals["total_generation_tokens"]["value"] == 185
    assert totals["embedding_input_tokens"] == {
        "value": 400, "estimated": True,
        "note": "the Gemini embedding API returns no usage metadata; 4 chars/token estimate",
    }


def test_a_missing_api_count_makes_the_total_null_not_a_guess():
    totals = eval_rag.usage_totals([_gen(100, None)])
    assert totals["output_tokens"]["value"] is None
    assert totals["total_generation_tokens"]["value"] is None
    cost = eval_rag.estimate_cost(totals, {"input": 1.0, "output": 1.0, "embed": None})
    assert cost["value"] is None and "incomplete" in cost["reason"]


def test_cost_is_null_without_prices_and_computed_with_them():
    totals = eval_rag.usage_totals([_gen(1_000_000, 100_000, 100_000)])
    assert eval_rag.estimate_cost(totals, {"input": None, "output": None})["value"] is None
    cost = eval_rag.estimate_cost(totals, {"input": 0.5, "output": 2.0, "embed": None})
    assert cost["value"] == pytest.approx(0.5 + 0.4)  # thinking billed at the output rate


def test_label_template_validates_and_counts_as_unfilled():
    template = eval_rag.label_template(["a.pdf"])
    assert eval_rag.validate_labels(template) == []
    assert eval_rag.filled_labels(template, "a.pdf") == []


def test_committed_labels_file_is_valid():
    from pathlib import Path

    data = json.loads((Path(eval_rag.ROOT) / "eval" / "labels.json").read_text())
    assert eval_rag.validate_labels(data) == []


@pytest.mark.parametrize("bad", [
    {"schema_version": 2, "documents": {}},
    {"schema_version": 1, "documents": []},
    {"schema_version": 1, "documents": {"a.pdf": {"labels": [{"query": "q", "kind": "other",
                                                               "answer_pages": [1]}]}}},
    {"schema_version": 1, "documents": {"a.pdf": {"labels": [{"query": "q", "kind": "topic",
                                                               "answer_pages": [0]}]}}},
])
def test_bad_labels_are_reported(bad):
    assert eval_rag.validate_labels(bad)


# --- dry run --------------------------------------------------------------------


class _RecordingFake(FakeGemini):
    """FakeGemini plus the usage records the real wrapper would write, and
    answers for the full-mode and judge prompts."""

    async def __call__(self, prompt, label=""):
        usage.record(_gen(len(prompt) // 4, 50, None))
        if label == "full:cards":
            return [{"question": "Full Q?", "answer": "Full A", "topic": "t",
                     "distractors": ["a", "b", "c"]}]
        if label == "judge":
            return {"verdict": "supported", "reason": "stated in source"}
        return await super().__call__(prompt, label)


def test_dry_run_reports_both_modes_with_nulls_where_unmeasurable(tmp_path, monkeypatch):
    monkeypatch.setattr(gemini, "generate_json", _RecordingFake(list(TOPIC_TEXT)))
    pdf = tmp_path / "bio.pdf"
    pdf.write_bytes(_pdf(list(TOPIC_TEXT.values())))
    labels = {"schema_version": 1, "documents": {"bio.pdf": {"labels": [
        {"query": "storming of the Bastille", "kind": "topic", "answer_pages": [2]},
        {"query": "how do chloroplasts make glucose", "kind": "question", "answer_pages": [1]},
    ]}}}

    report = eval_rag.run_eval(
        _TestSession, [pdf], labels, ["full", "rag"], k=2, runs=2, judge=True,
        prices={"input": None, "output": None, "embed": None}, seed=1, sample_size=5,
    )

    full, rag = report["summary"]["full"], report["summary"]["rag"]
    assert full["runs"] == rag["runs"] == 2
    assert full["failed_runs"] == rag["failed_runs"] == 0, report["runs"]

    assert full["recall_at_k"] == {"value": None, "reason": "full mode does not retrieve"}
    assert full["faithfulness"]["value"] is None
    assert rag["recall_at_k"]["value"] is not None
    assert rag["recall_at_k"]["n_labels"] == 4  # 2 labels x 2 runs
    assert rag["faithfulness"]["value"] == 1.0

    for s in (full, rag):
        assert s["tokens_per_upload_mean"]["value"] > 0
        assert "no prices" in s["estimated_cost_per_upload_usd_mean"]["reason"]
        assert s["latency"]["n"] == 2
    # Full mode never embeds; rag does, and that is reported as an estimate.
    assert full["embedding_input_tokens_per_upload_mean"]["value"] == 0
    assert rag["embedding_input_tokens_per_upload_mean"]["value"] > 0
    # rag spends more generation calls (topics + one per topic) than full's one.
    rag_run = next(r for r in report["runs"] if r["mode"] == "rag")
    assert rag_run["usage"]["generation_calls"] > 1
    # Judging is accounted separately, not as upload cost.
    assert rag_run["judge_calls"] == rag_run["card_count"]

    assert len(report["manual_sample"]) == 5
    assert all(s["manual_check"]["answer_correct"] is None for s in report["manual_sample"])

    md = eval_rag.markdown_report(report)
    assert "| Recall@2 |" in md
    assert "null — full mode does not retrieve" in md
    json.dumps(report, default=str)  # serialisable


def test_a_failing_run_is_recorded_not_raised(tmp_path, monkeypatch):
    async def broken(prompt, label=""):
        raise RuntimeError("quota exhausted")

    monkeypatch.setattr(gemini, "generate_json", broken)
    pdf = tmp_path / "bio.pdf"
    pdf.write_bytes(_pdf(list(TOPIC_TEXT.values())))

    report = eval_rag.run_eval(_TestSession, [pdf], None, ["full"], k=2, runs=1, judge=False,
                               prices={}, seed=0)

    [run] = report["runs"]
    assert run["ok"] is False and "quota exhausted" in run["error"]
    assert report["summary"]["full"]["failed_runs"] == 1
    assert report["summary"]["full"]["latency"]["p50_seconds"]["value"] is None


def test_eval_refuses_a_database_not_named_eval():
    with pytest.raises(SystemExit, match="_eval"):
        eval_rag._session_factory("postgresql+psycopg://u:p@localhost/marigold")
