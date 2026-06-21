"""Offline retrieval eval: recall@k + MRR over a ground-truth set.

Ground truth = JSONL, one object per line:
    {"query": "<text>", "relevant_ids": ["<article-uuid>", ...], "lang": "en"}

Build it cheaply by sampling story clusters: a multi-article cluster about an
event becomes one query, and its member article ids are the relevant set. This is
the gate that decides whether the retrieval engine is "great" before we ship.

Runs BOTH arms (rerank off / on) and prints a comparison so the reranker lift is
measured, not assumed. Retrieval-only — no LLM calls.

Run (needs tunnel + LaBSE):
    .venv/Scripts/python eval/run_eval.py eval/ground_truth.jsonl
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import load_settings  # noqa: E402
from app.db import connect  # noqa: E402
from app.embedding import LabseEmbedder  # noqa: E402
from app.retrieval import retrieve_and_curate  # noqa: E402


def recall_at_k(retrieved_ids: list[str], relevant_ids: list[str], k: int) -> float:
    top = set(retrieved_ids[:k])
    relevant = set(relevant_ids)
    return len(top & relevant) / max(1, len(relevant))


def reciprocal_rank(retrieved_ids: list[str], relevant_ids: list[str]) -> float:
    relevant = set(relevant_ids)
    for i, doc_id in enumerate(retrieved_ids, start=1):
        if doc_id in relevant:
            return 1.0 / i
    return 0.0


async def _evaluate(conn, settings, rows, qvecs, rerank_enabled: bool) -> dict:
    rec10s, rec20s, hits, rrs, xling = [], [], [], [], []
    for row, qvec in zip(rows, qvecs):
        docs = await retrieve_and_curate(
            conn, settings, row["query"], qvec, None,
            top_k=max(20, settings.top_k), rerank_enabled=rerank_enabled,
        )
        ids = [d.id for d in docs]
        rel = row["relevant_ids"]
        r10 = recall_at_k(ids, rel, 10)
        rec10s.append(r10)
        rec20s.append(recall_at_k(ids, rel, 20))
        hits.append(1.0 if set(ids[:10]) & set(rel) else 0.0)
        rrs.append(reciprocal_rank(ids, rel))
        if row.get("lang") and row["lang"] != "en":
            xling.append(r10)
    n = max(1, len(rows))
    return {
        "hit@10": sum(hits) / n,
        "recall@10": sum(rec10s) / n,
        "recall@20": sum(rec20s) / n,
        "MRR": sum(rrs) / n,
        "xling_recall@10": (sum(xling) / len(xling)) if xling else None,
    }


def _fmt(metrics: dict) -> str:
    x = metrics["xling_recall@10"]
    return (
        f"hit@10={metrics['hit@10']:.3f}  recall@10={metrics['recall@10']:.3f}  "
        f"recall@20={metrics['recall@20']:.3f}  MRR={metrics['MRR']:.3f}"
        + (f"  xling_recall@10={x:.3f}" if x is not None else "")
    )


async def main(path: str) -> None:
    settings = load_settings()
    embedder = LabseEmbedder(settings.embed_model)
    rows = [
        json.loads(line)
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    qvecs = [embedder.embed(r["query"]) for r in rows]  # embed once, reuse both arms

    async with connect(settings) as conn:
        print(f"queries={len(rows)}  (running both arms — rerank ON is slow on CPU)\n")
        off = await _evaluate(conn, settings, rows, qvecs, rerank_enabled=False)
        print(f"  rerank OFF : {_fmt(off)}")
        on = await _evaluate(conn, settings, rows, qvecs, rerank_enabled=True)
        print(f"  rerank ON  : {_fmt(on)}")

    delta = (on["recall@10"] - off["recall@10"]) * 100
    dmrr = (on["MRR"] - off["MRR"]) * 100
    print(f"\n  rerank lift: recall@10 {delta:+.1f} pts | MRR {dmrr:+.1f} pts")
    print(
        "\nnote: recall is vs EXACT cluster membership (strict lower bound — on-topic "
        "non-member hits count as misses). hit@10/MRR are the operative Q&A metrics."
    )


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "eval/ground_truth.example.jsonl"))
