"""Compare GENERATION_MODE=full against GENERATION_MODE=rag on real PDFs.

    python -m scripts.eval_rag                       # every PDF in eval/docs/
    python -m scripts.eval_rag --write-label-template  # skeleton labels for them
    python -m scripts.eval_rag --price-input 0.30 --price-output 2.50 --price-embed 0.15

Makes real Gemini calls (generation, embeddings, and the faithfulness judge),
so it costs money and needs GEMINI_API_KEY.

Metrics, and exactly where each number comes from:

* Recall@k (rag only) — for each labelled query in eval/labels.json, embed it,
  retrieve the document's top-k chunks the way generation does, and count a
  hit if any retrieved chunk's page range contains a labelled answer page.
  Reported per document and overall. Full mode retrieves nothing: null.
* Faithfulness (rag only) — an LLM judge reads each card and ONLY the chunks
  it cites, and says whether the answer is supported. Full-mode cards cite
  nothing, so there is nothing to judge them against: null. The judge is a
  Gemini model grading Gemini output, which can be lenient — that is why a
  random sample of cards is also dumped for checking by hand.
* Tokens per upload — summed from the API's own usage metadata on every
  generation call (prompt + output + thinking). Embedding calls return no
  usage metadata on the Gemini API, so their input size is reported
  separately, labelled as an estimate (4 chars/token), never folded in.
* Estimated cost — only if per-million-token prices are supplied. Prices are
  not hard-coded: they change, and a stale number in a report is worse than
  none. Thinking tokens are priced at the output rate, which is how Gemini
  bills them.
* Generation latency p50/p95 — wall time of the work generation does after
  upload: for full, the one Gemini call; for rag, embedding the chunks, topics,
  retrieval and the per-topic calls. Nearest-rank percentiles over every
  (document, run); the sample size is reported beside them, and with fewer
  than 20 samples p95 is just the maximum and is flagged as such.

Anything that cannot be measured is reported as null with a reason. Nothing is
filled in by estimate unless it is labelled as one.

Writes to its own database: EVAL_DATABASE_URL (default: the compose server's
marigold_eval), which must be named *_eval. Tables are created there if
missing; each run adds its own documents and leaves them for inspection.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import random
import statistics
import sys
import time
import traceback
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DOCS = ROOT / "eval" / "docs"
DEFAULT_LABELS = ROOT / "eval" / "labels.json"
DEFAULT_OUT = ROOT / "eval" / "results"
DEFAULT_EVAL_DB = "postgresql+psycopg://marigold:devpass@localhost:55432/marigold_eval"

SAMPLE_SIZE = 20
LABELS_SCHEMA_VERSION = 1


def _null(reason: str) -> Dict[str, Any]:
    return {"value": None, "reason": reason}


def _value(v: Any, **extra) -> Dict[str, Any]:
    return {"value": v, **extra}


# --- pure metric helpers (unit-tested) ------------------------------------------


def nearest_rank_percentile(values: Sequence[float], q: float) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(q * len(ordered)))
    return ordered[rank - 1]


def latency_summary(samples: Sequence[float]) -> Dict[str, Any]:
    if not samples:
        return {"p50_seconds": _null("no successful runs"), "p95_seconds": _null("no successful runs"),
                "n": 0}
    p95 = nearest_rank_percentile(samples, 0.95)
    p95_entry = _value(round(p95, 3))
    if len(samples) < 20:
        p95_entry["note"] = f"only {len(samples)} samples: nearest-rank p95 is the maximum"
    return {
        "p50_seconds": _value(round(nearest_rank_percentile(samples, 0.50), 3)),
        "p95_seconds": p95_entry,
        "n": len(samples),
    }


def page_hit(chunk_pages: Sequence[tuple], answer_pages: Sequence[int]) -> bool:
    return any(start <= page <= end for start, end in chunk_pages for page in answer_pages)


def usage_totals(calls: Sequence[Any]) -> Dict[str, Any]:
    """Sum one upload's usage records. A missing API count makes the total null."""
    gen = [c for c in calls if c.kind == "generate"]
    emb = [c for c in calls if c.kind == "embed"]
    out: Dict[str, Any] = {"generation_calls": len(gen), "embedding_calls": len(emb)}
    for field in ("prompt_tokens", "output_tokens", "thinking_tokens"):
        values = [getattr(c, field) for c in gen]
        if field == "thinking_tokens":
            # The API omits thoughts_token_count when the model did no
            # thinking, rather than sending 0. Counted as 0, and said so.
            out[field] = _value(sum(v or 0 for v in values))
            missing = sum(v is None for v in values)
            if missing:
                out[field]["note"] = f"{missing} call(s) reported no thinking count; counted as 0"
        elif any(v is None for v in values):
            out[field] = _null("the API did not report this count for every call")
        else:
            out[field] = _value(sum(values))
    if all(out[f]["value"] is not None for f in ("prompt_tokens", "output_tokens", "thinking_tokens")):
        out["total_generation_tokens"] = _value(
            out["prompt_tokens"]["value"] + out["output_tokens"]["value"]
            + out["thinking_tokens"]["value"]
        )
    else:
        out["total_generation_tokens"] = _null("a component count is missing")
    out["embedding_input_tokens"] = _value(
        sum(c.estimated_input_tokens or 0 for c in emb),
        estimated=True,
        note="the Gemini embedding API returns no usage metadata; 4 chars/token estimate",
    )
    return out


def estimate_cost(totals: Dict[str, Any], prices: Dict[str, Optional[float]]) -> Dict[str, Any]:
    if prices.get("input") is None or prices.get("output") is None:
        return _null("no prices supplied (--price-input / --price-output, USD per 1M tokens)")
    if totals["total_generation_tokens"]["value"] is None:
        return _null("token counts incomplete: " + totals["total_generation_tokens"]["reason"])
    usd = (
        totals["prompt_tokens"]["value"] * prices["input"]
        + (totals["output_tokens"]["value"] + totals["thinking_tokens"]["value"]) * prices["output"]
    ) / 1_000_000
    entry = _value(round(usd, 6), currency="USD", includes_embeddings=False)
    if totals["embedding_calls"]:
        if prices.get("embed") is None:
            entry["note"] = "embedding cost excluded: no --price-embed supplied"
        else:
            emb = totals["embedding_input_tokens"]["value"] * prices["embed"] / 1_000_000
            entry["value"] = round(usd + emb, 6)
            entry["includes_embeddings"] = True
            entry["note"] = "embedding share is from estimated tokens"
    return entry


# --- labels -----------------------------------------------------------------------


def label_template(pdf_names: Sequence[str]) -> Dict[str, Any]:
    return {
        "schema_version": LABELS_SCHEMA_VERSION,
        "description": (
            "Ground truth for retrieval Recall@k. For each PDF in eval/docs/, list "
            "queries (a topic or a question) and the 1-based page number(s) where "
            "the answer appears. A label with an empty answer_pages is treated as "
            "unfilled and skipped."
        ),
        "documents": {
            name: {
                "labels": [
                    {"query": "", "kind": "question", "answer_pages": []},
                    {"query": "", "kind": "topic", "answer_pages": []},
                ]
            }
            for name in pdf_names
        },
    }


def validate_labels(data: Dict[str, Any]) -> List[str]:
    """Problems with a labels file; empty when it is usable."""
    problems = []
    if data.get("schema_version") != LABELS_SCHEMA_VERSION:
        problems.append(f"schema_version must be {LABELS_SCHEMA_VERSION}")
    docs = data.get("documents")
    if not isinstance(docs, dict):
        return problems + ["'documents' must be an object keyed by PDF filename"]
    for name, entry in docs.items():
        labels = entry.get("labels") if isinstance(entry, dict) else None
        if not isinstance(labels, list):
            problems.append(f"{name}: 'labels' must be a list")
            continue
        for i, label in enumerate(labels):
            where = f"{name} label {i}"
            if not isinstance(label, dict):
                problems.append(f"{where}: must be an object")
                continue
            if label.get("kind") not in ("question", "topic"):
                problems.append(f"{where}: kind must be 'question' or 'topic'")
            if not isinstance(label.get("query"), str):
                problems.append(f"{where}: query must be a string")
            pages = label.get("answer_pages")
            if not isinstance(pages, list) or not all(
                isinstance(p, int) and not isinstance(p, bool) and p >= 1 for p in pages
            ):
                problems.append(f"{where}: answer_pages must be a list of page numbers >= 1")
    return problems


def filled_labels(data: Dict[str, Any], pdf_name: str) -> List[Dict[str, Any]]:
    entry = (data.get("documents") or {}).get(pdf_name) or {}
    return [
        l for l in entry.get("labels", [])
        if isinstance(l, dict) and str(l.get("query", "")).strip() and l.get("answer_pages")
    ]


# --- the run ------------------------------------------------------------------------


def _judge_prompt(question: str, answer: str, sources: Sequence[str]) -> str:
    joined = "\n\n".join(f"<source>\n{s}\n</source>" for s in sources)
    return f"""
You are checking a flashcard against its cited sources. Judge ONLY from the
sources below — not from your own knowledge, even if the answer is true.

"supported": every claim in the answer is stated in or directly entailed by
the sources. "partial": some of it is, some is not. "unsupported": the
sources do not back the answer.

Question: {question}
Answer: {answer}

Sources:
{joined}

Return ONLY a JSON object: {{"verdict": "supported" | "partial" | "unsupported", "reason": "one sentence"}}
"""


async def _judge(gemini_mod, card: Dict[str, Any]) -> Dict[str, Any]:
    try:
        raw = await gemini_mod.generate_json(
            _judge_prompt(card["question"], card["answer"], [s["text"] for s in card["sources"]]),
            label="judge",
        )
        verdict = str(raw.get("verdict", "")).strip().lower() if isinstance(raw, dict) else ""
        if verdict not in ("supported", "partial", "unsupported"):
            return {"verdict": None, "reason": f"unparseable judge output: {raw!r}"[:300]}
        return {"verdict": verdict, "reason": str(raw.get("reason", ""))[:500]}
    except Exception as exc:  # recorded per card, never fatal
        return {"verdict": None, "reason": f"judge call failed: {exc}"[:300]}


async def _run_one(session_factory, user_id: int, pdf: Path, mode: str, labels, k: int,
                   judge: bool) -> Dict[str, Any]:
    from backend import gemini
    from backend.chunking import chunk_pages, extract_pages, strip_nul
    from backend.config import get_settings
    from backend.embeddings import aembed_query, embed_document_chunks
    from backend.generation import draft_cards
    from backend.models import Document, DocumentChunk
    from backend.retrieval import retrieve_chunks
    from backend.usage import track_usage

    settings = get_settings()
    record: Dict[str, Any] = {"document": pdf.name, "mode": mode}
    db = session_factory()
    try:
        pages = extract_pages(pdf.read_bytes())
        text = strip_nul("\n".join(pages)).strip()
        doc = Document(user_id=user_id, filename=pdf.name, status="eval", page_count=len(pages),
                       extracted_text=text)
        db.add(doc)
        db.flush()
        chunks = chunk_pages(pages, settings.chunk_target_tokens, settings.chunk_max_tokens,
                             settings.chunk_overlap_tokens)
        for c in chunks:
            db.add(DocumentChunk(document_id=doc.id, chunk_index=c.chunk_index,
                                 page_start=c.page_start, page_end=c.page_end, text=c.text,
                                 token_count=c.token_count))
        db.commit()
        record.update(document_id=doc.id, pages=len(pages), chunks=len(chunks),
                      estimated_document_tokens=sum(c.token_count for c in chunks))

        with track_usage() as tracker:
            started = time.perf_counter()
            if mode == "rag":
                await embed_document_chunks(db, doc)  # part of rag's cost; full never needs it
            drafted = await draft_cards(db, doc, full_generator=gemini.generate_flashcards,
                                        mode=mode)
            latency = time.perf_counter() - started
        db.commit()

        totals = usage_totals(tracker.calls)
        record.update(
            ok=True,
            mode_ran=drafted.mode,
            fallback_reason=drafted.fallback_reason,
            latency_seconds=round(latency, 3),
            usage=totals,
            calls=[asdict(c) for c in tracker.calls],
            card_count=len(drafted.cards),
            rejected_cards=len(drafted.rejected),
            topics=drafted.topics,
        )

        chunk_by_id = {c.id: c for c in doc.chunks}
        cards = []
        for d in drafted.cards:
            cards.append({
                "question": d.question, "answer": d.answer, "topic": d.topic,
                "distractors": d.distractors,
                "sources": [
                    {"chunk_id": cid, "page_start": chunk_by_id[cid].page_start,
                     "page_end": chunk_by_id[cid].page_end, "text": chunk_by_id[cid].text}
                    for cid in d.chunk_ids if cid in chunk_by_id
                ],
            })

        # Faithfulness: rag only, judged in a separate tracker so judging is
        # never counted as the cost of an upload.
        if mode == "rag" and judge:
            with track_usage() as judge_tracker:
                for card in cards:
                    card["judge"] = await _judge(gemini, card) if card["sources"] else {
                        "verdict": None, "reason": "card has no sources"}
            record["judge_calls"] = len(judge_tracker.calls)
        record["cards"] = cards

        # Recall@k: rag only (full retrieves nothing).
        if mode == "rag":
            doc_labels = filled_labels(labels, pdf.name) if labels else []
            if not doc_labels:
                record["recall"] = _null("no filled labels for this document in eval/labels.json")
            else:
                per = []
                for label in doc_labels:
                    vector = await aembed_query(label["query"])
                    hits = retrieve_chunks(db, doc.id, vector, k)
                    ranges = [(h.chunk.page_start, h.chunk.page_end) for h in hits]
                    per.append({"query": label["query"], "kind": label["kind"],
                                "answer_pages": label["answer_pages"], "retrieved_pages": ranges,
                                "hit": page_hit(ranges, label["answer_pages"])})
                record["recall"] = _value(sum(p["hit"] for p in per) / len(per),
                                          k=k, n=len(per), labels=per)
        else:
            record["recall"] = _null("full mode does not retrieve")
    except Exception as exc:
        db.rollback()
        record.update(ok=False, error=f"{type(exc).__name__}: {exc}",
                      traceback=traceback.format_exc(limit=5))
    finally:
        db.close()
    return record


def _faithfulness(records: Sequence[Dict[str, Any]], mode: str, judged: bool) -> Dict[str, Any]:
    if mode != "rag":
        return _null("full-mode cards have no citations to judge against")
    if not judged:
        return _null("judge disabled (--no-judge)")
    verdicts = [c.get("judge", {}).get("verdict") for r in records if r.get("ok")
                for c in r.get("cards", [])]
    counted = [v for v in verdicts if v is not None]
    if not counted:
        return _null("no card received a usable verdict")
    return _value(
        round(sum(v == "supported" for v in counted) / len(counted), 4),
        definition="share of judged cards whose answer is fully supported by their cited chunks",
        judged=len(counted), unjudged=len(verdicts) - len(counted),
        partial=sum(v == "partial" for v in counted),
        unsupported=sum(v == "unsupported" for v in counted),
    )


def summarise(records: Sequence[Dict[str, Any]], modes: Sequence[str], prices, judged: bool):
    summary = {}
    for mode in modes:
        runs = [r for r in records if r["mode"] == mode]
        ok = [r for r in runs if r.get("ok")]
        tokens = [r["usage"]["total_generation_tokens"]["value"] for r in ok]
        complete = [t for t in tokens if t is not None]
        costs = [estimate_cost(r["usage"], prices) for r in ok]
        cost_values = [c["value"] for c in costs if c["value"] is not None]
        recalls = [r["recall"] for r in ok if r.get("recall", {}).get("value") is not None]
        label_results = [l for r in recalls for l in r["labels"]]
        summary[mode] = {
            "runs": len(runs),
            "failed_runs": len(runs) - len(ok),
            "fell_back_to_full": sum(1 for r in ok if r.get("mode_ran") != mode),
            "cards_per_upload_mean": (round(statistics.mean(r["card_count"] for r in ok), 2)
                                      if ok else None),
            "rejected_cards_total": sum(r.get("rejected_cards", 0) for r in ok),
            "tokens_per_upload_mean": (
                _value(round(statistics.mean(complete), 1), n=len(complete))
                if complete and len(complete) == len(ok)
                else _null("no successful runs" if not ok else "token counts missing for some runs")
            ),
            "embedding_input_tokens_per_upload_mean": (
                _value(round(statistics.mean(
                    r["usage"]["embedding_input_tokens"]["value"] for r in ok), 1), estimated=True)
                if ok else _null("no successful runs")
            ),
            "estimated_cost_per_upload_usd_mean": (
                _value(round(statistics.mean(cost_values), 6), n=len(cost_values))
                if cost_values and len(cost_values) == len(ok)
                else (costs[0] if costs and costs[0]["value"] is None
                      else _null("no successful runs"))
            ),
            "latency": latency_summary([r["latency_seconds"] for r in ok]),
            "recall_at_k": (
                _value(round(sum(l["hit"] for l in label_results) / len(label_results), 4),
                       n_labels=len(label_results), n_documents=len(recalls))
                if label_results else
                _null("full mode does not retrieve" if mode == "full"
                      else "no filled labels in eval/labels.json")
            ),
            "faithfulness": _faithfulness(runs, mode, judged),
        }
    return summary


def manual_sample(records: Sequence[Dict[str, Any]], size: int, seed: int) -> List[Dict[str, Any]]:
    pool = [
        {"document": r["document"], "mode": r["mode"], **card}
        for r in records if r.get("ok") for card in r.get("cards", [])
    ]
    rng = random.Random(seed)
    picked = rng.sample(pool, min(size, len(pool)))
    for item in picked:
        item["manual_check"] = {"answer_correct": None, "supported_by_sources": None, "notes": ""}
    return picked


def _fmt(entry: Any) -> str:
    if isinstance(entry, dict) and "value" in entry:
        if entry["value"] is None:
            return f"null — {entry.get('reason', '')}"
        extra = ""
        if entry.get("estimated"):
            extra = " (estimated)"
        if entry.get("note"):
            extra += f" ({entry['note']})"
        return f"{entry['value']}{extra}"
    return "null" if entry is None else str(entry)


def markdown_report(report: Dict[str, Any]) -> str:
    modes = report["config"]["modes"]
    rows = [
        ("Runs (failed)", lambda s: f"{s['runs']} ({s['failed_runs']})"),
        ("Fell back to full", lambda s: str(s["fell_back_to_full"])),
        ("Cards per upload (mean)", lambda s: _fmt(s["cards_per_upload_mean"])),
        ("Cards rejected for citations", lambda s: str(s["rejected_cards_total"])),
        (f"Recall@{report['config']['k']}", lambda s: _fmt(s["recall_at_k"])),
        ("Faithfulness (judge)", lambda s: _fmt(s["faithfulness"])),
        ("Generation tokens / upload", lambda s: _fmt(s["tokens_per_upload_mean"])),
        ("Embedding input tokens / upload", lambda s: _fmt(s["embedding_input_tokens_per_upload_mean"])),
        ("Est. cost / upload (USD)", lambda s: _fmt(s["estimated_cost_per_upload_usd_mean"])),
        ("Latency p50 (s)", lambda s: _fmt(s["latency"]["p50_seconds"])),
        ("Latency p95 (s)", lambda s: _fmt(s["latency"]["p95_seconds"]) + f" [n={s['latency']['n']}]"),
    ]
    lines = [
        f"# RAG vs full-document generation — {report['generated_at']}",
        "",
        f"Documents: {len(report['config']['documents'])} · runs per document: "
        f"{report['config']['runs']} · model: `{report['config']['gemini_model']}` · "
        f"embeddings: `{report['config']['embedding_model']}` · k={report['config']['k']}",
        "",
        "| Metric | " + " | ".join(modes) + " |",
        "|---|" + "---|" * len(modes),
    ]
    for name, fn in rows:
        lines.append(f"| {name} | " + " | ".join(fn(report["summary"][m]) for m in modes) + " |")
    lines += [
        "",
        "Null means not measured; the reason is given. Token counts are the API's own usage",
        "metadata; anything estimated is marked. The faithfulness judge is a Gemini model",
        "grading Gemini output, so treat it as a screen — see `manual_sample.json` for",
        f"{len(report['manual_sample'])} random cards to check by hand.",
        "",
        "## Per document",
        "",
        "| Document | Mode | OK | Cards | Rejected | Latency (s) | Gen. tokens | Recall |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in report["runs"]:
        if r.get("ok"):
            lines.append(
                f"| {r['document']} | {r['mode']} | yes | {r['card_count']} | {r['rejected_cards']} | "
                f"{r['latency_seconds']} | {_fmt(r['usage']['total_generation_tokens'])} | "
                f"{_fmt(r['recall'])} |"
            )
        else:
            lines.append(f"| {r['document']} | {r['mode']} | **no**: {r['error'][:80]} | | | | | |")
    return "\n".join(lines) + "\n"


def run_eval(session_factory, pdfs: Sequence[Path], labels: Optional[Dict[str, Any]],
             modes: Sequence[str], k: int, runs: int, judge: bool, prices, seed: int,
             sample_size: int = SAMPLE_SIZE) -> Dict[str, Any]:
    from backend.config import get_settings
    from backend.models import User

    settings = get_settings()
    db = session_factory()
    try:
        email = f"eval-{datetime.now(timezone.utc):%Y%m%d%H%M%S%f}@eval.invalid"
        user = User(email=email, email_verified=True, name="eval")
        db.add(user)
        db.commit()
        user_id = user.id
    finally:
        db.close()

    records = []
    original_k = settings.rag_top_k
    settings.rag_top_k = k
    try:
        for pdf in pdfs:
            for mode in modes:
                for run in range(runs):
                    print(f"  {pdf.name} · {mode} · run {run + 1}/{runs}", file=sys.stderr)
                    rec = asyncio.run(_run_one(session_factory, user_id, pdf, mode, labels, k, judge))
                    rec["run"] = run + 1
                    records.append(rec)
    finally:
        settings.rag_top_k = original_k

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "config": {
            "documents": [p.name for p in pdfs], "modes": list(modes), "runs": runs, "k": k,
            "cards_per_upload": settings.cards_per_upload, "rag_topic_count": settings.rag_topic_count,
            "gemini_model": settings.gemini_model, "embedding_model": settings.gemini_embedding_model,
            "chunking": {"target": settings.chunk_target_tokens, "max": settings.chunk_max_tokens,
                         "overlap": settings.chunk_overlap_tokens, "unit": "estimated tokens"},
            "prices_usd_per_million_tokens": prices, "judge": judge, "seed": seed,
        },
        "summary": summarise(records, modes, prices, judge),
        "manual_sample": manual_sample(records, sample_size, seed),
        "runs": records,
    }


def _session_factory(url: str):
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker

    from backend.database import Base
    from backend import models  # noqa: F401

    name = urlparse(url).path.lstrip("/")
    if not name.endswith("_eval"):
        sys.exit(f"EVAL_DATABASE_URL must name a database ending in '_eval' (got {name!r}); "
                 "the eval writes documents and cards there.")
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--docs", type=Path, default=DEFAULT_DOCS)
    parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--modes", nargs="+", choices=["full", "rag"], default=["full", "rag"])
    parser.add_argument("--k", type=int, default=None, help="top-k (default: RAG_TOP_K)")
    parser.add_argument("--runs", type=int, default=1, help="runs per document and mode")
    parser.add_argument("--no-judge", action="store_true")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--price-input", type=float, default=None, help="USD per 1M input tokens")
    parser.add_argument("--price-output", type=float, default=None,
                        help="USD per 1M output tokens (thinking billed at this rate)")
    parser.add_argument("--price-embed", type=float, default=None,
                        help="USD per 1M embedding input tokens")
    parser.add_argument("--write-label-template", action="store_true",
                        help="write a skeleton labels file for the PDFs in --docs and exit")
    args = parser.parse_args(argv)

    pdfs = sorted(p for p in args.docs.glob("*.pdf"))
    if args.write_label_template:
        if args.labels.exists():
            sys.exit(f"{args.labels} already exists; not overwriting your labels.")
        args.labels.write_text(json.dumps(label_template([p.name for p in pdfs]), indent=2) + "\n")
        print(f"wrote {args.labels} for {len(pdfs)} PDF(s)")
        return 0
    if not pdfs:
        sys.exit(f"no PDFs in {args.docs}")

    labels = None
    if args.labels.exists():
        labels = json.loads(args.labels.read_text())
        problems = validate_labels(labels)
        if problems:
            sys.exit("labels file has problems:\n  " + "\n  ".join(problems))

    os.environ.setdefault("DATABASE_URL", os.environ.get("EVAL_DATABASE_URL", DEFAULT_EVAL_DB))
    from backend.config import get_settings

    settings = get_settings()
    factory = _session_factory(os.environ.get("EVAL_DATABASE_URL", DEFAULT_EVAL_DB))
    prices = {"input": args.price_input, "output": args.price_output, "embed": args.price_embed}

    report = run_eval(factory, pdfs, labels, args.modes, args.k or settings.rag_top_k, args.runs,
                      not args.no_judge, prices, args.seed)

    out_dir = args.out / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.json").write_text(json.dumps(report, indent=2, default=str) + "\n")
    (out_dir / "report.md").write_text(markdown_report(report))
    (out_dir / "manual_sample.json").write_text(json.dumps(report["manual_sample"], indent=2) + "\n")
    print(markdown_report(report))
    print(f"wrote {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
