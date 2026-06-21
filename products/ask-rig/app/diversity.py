"""Diversity pipeline: semantic dedup → MMR → source quota → context assembly.

All pure functions — no model calls, no I/O, deterministic given the same input.
Operates on RetrievedDoc lists sorted by score descending (as returned by RRF/rerank).
"""
from __future__ import annotations

import math
import re
from collections import Counter

from app.schemas import RetrievedDoc


# ---------------------------------------------------------------------------
# text helpers (no external deps)
# ---------------------------------------------------------------------------

def _tokens(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())


def _jaccard(a: set[str], b: set[str]) -> float:
    union = a | b
    return len(a & b) / max(1, len(union))


def _build_idf(corpora: list[list[str]]) -> dict[str, float]:
    n = len(corpora)
    df: Counter[str] = Counter()
    for tokens in corpora:
        df.update(set(tokens))
    return {t: math.log((n + 1) / (cnt + 1)) + 1.0 for t, cnt in df.items()}


def _tfidf(tokens: list[str], idf: dict[str, float]) -> dict[str, float]:
    tf = Counter(tokens)
    total = max(1, sum(tf.values()))
    return {t: (c / total) * idf.get(t, 1.0) for t, c in tf.items()}


def _cos(a: dict[str, float], b: dict[str, float]) -> float:
    dot = sum(a[k] * b[k] for k in a if k in b)
    mag = math.sqrt(sum(v * v for v in a.values())) * math.sqrt(sum(v * v for v in b.values()))
    return dot / max(1e-9, mag)


def _text(doc: RetrievedDoc) -> str:
    return (doc.title or "") + " " + (doc.snippet or "")


# ---------------------------------------------------------------------------
# pipeline stages
# ---------------------------------------------------------------------------

def semantic_dedup(docs: list[RetrievedDoc], threshold: float = 0.65) -> list[RetrievedDoc]:
    """Drop near-duplicate reprints using title word-set Jaccard similarity.

    Keeps the first (higher-scored) doc when two exceed the threshold.
    O(n²) on the candidate list — fine for n ≤ 100.
    """
    kept: list[RetrievedDoc] = []
    kept_sets: list[set[str]] = []
    for doc in docs:
        words = set(_tokens(doc.title or doc.snippet or ""))
        if not any(_jaccard(words, seen) >= threshold for seen in kept_sets):
            kept.append(doc)
            kept_sets.append(words)
    return kept


def mmr_select(
    docs: list[RetrievedDoc],
    top_n: int,
    lam: float = 0.65,
) -> list[RetrievedDoc]:
    """Maximal Marginal Relevance over TF-IDF title+snippet vectors.

    λ=1 → pure score order; λ=0 → pure diversity.
    λ=0.65 keeps quality dominant while breaking score-collapse on near-reprints.
    Greedy O(n²) — fine for n ≤ 50.
    """
    if not docs or top_n <= 0:
        return []
    top_n = min(top_n, len(docs))

    corpus = [_tokens(_text(d)) for d in docs]
    idf = _build_idf(corpus)
    vecs = [_tfidf(t, idf) for t in corpus]
    max_score = max(d.score for d in docs) or 1.0
    rel = [d.score / max_score for d in docs]

    selected: list[int] = []
    remaining = list(range(len(docs)))

    while len(selected) < top_n and remaining:
        if not selected:
            best = max(remaining, key=lambda i: rel[i])
        else:
            sel_snap = list(selected)
            best = max(
                remaining,
                key=lambda i, s=sel_snap: (
                    lam * rel[i] - (1 - lam) * max(_cos(vecs[i], vecs[j]) for j in s)
                ),
            )
        selected.append(best)
        remaining.remove(best)

    return [docs[i] for i in selected]


def facet_quota(docs: list[RetrievedDoc], max_per_source: int = 2) -> list[RetrievedDoc]:
    """Cap docs per source_id so no single outlet dominates the context."""
    counts: Counter[str] = Counter()
    kept: list[RetrievedDoc] = []
    for doc in docs:
        sid = doc.source_id or "_unknown"
        if counts[sid] < max_per_source:
            kept.append(doc)
            counts[sid] += 1
    return kept


def assemble(docs: list[RetrievedDoc]) -> list[RetrievedDoc]:
    """Counter lost-in-the-middle: place best first, 2nd-best last, rest in middle.

    LLMs attend most to the beginning and end of context; weakest docs go middle.
    """
    if len(docs) <= 2:
        return docs
    return [docs[0], *docs[2:], docs[1]]
