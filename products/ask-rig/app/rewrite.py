"""Query rewriting / RAG-Fusion — turn one (often vague) query into a few sharper,
complementary search variants, so vague questions get focused and recall improves.
Uses the LLM we already have; degrades to [] on any failure (caller falls back to
the raw query)."""
from __future__ import annotations

import re

from app.llm import LLMProvider

_REWRITE_SYSTEM = (
    "You rewrite a user's search query into 3 alternative queries that improve retrieval over an "
    "Indian multilingual NEWS corpus, while PRESERVING the user's intent and breadth.\n"
    "- If the query is BROAD ('latest news', 'top stories', 'what's happening in X', 'latest of X'): "
    "produce 3 BROAD coverage angles — e.g. major developments, politics/governance, and key "
    "people/events for that subject. Do NOT invent narrow verticals (weather, traffic, sports, "
    "horoscopes, crime) unless the user explicitly asked — that skews the results.\n"
    "- If the query is SPECIFIC: produce 3 sharper variants on that same topic.\n"
    "Keep each query under 9 words. Output ONLY the 3 queries, one per line, no numbering or commentary."
)


def rewrite_query(llm: LLMProvider, query: str, n: int = 3) -> list[str]:
    try:
        raw = llm.complete(_REWRITE_SYSTEM, f"Query: {query}")
    except Exception:  # noqa: BLE001 - rewriting is best-effort; never block the search
        return []
    seen = {query.strip().lower()}
    out: list[str] = []
    for line in raw.splitlines():
        v = re.sub(r"^[\s\-\d\.\)\*•]+", "", line).strip().strip('"').strip()
        key = v.lower()
        if v and key not in seen:
            seen.add(key)
            out.append(v)
        if len(out) >= n:
            break
    return out
