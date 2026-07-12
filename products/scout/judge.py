"""LLM judge — sharpens the SUBJECTIVE dimensions keyword filters can't:
  - sentiment: is this genuinely a hostile/hateful/harmful COMMENT about the subject (not news)?
  - perspective: is this really about the topic AND reflecting the anchor's viewpoint?

One batched call per source (fast Groq model). ALWAYS degrades gracefully: if the pool is
unreachable / no key / errors, it falls back to the keyword filters (the keyword result is the
floor). The response is tagged "judged by llm|keyword" so it's transparent which ran.
"""
from __future__ import annotations

import os
import re

import httpx

import products.scout.plan as P

_GROQ_KEY = (os.environ.get("GROQ_API_KEYS", "") or os.environ.get("GROQ_API_KEY", "")).split(",")[0].strip()
_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
_MODEL = os.environ.get("SCOUT_JUDGE_MODEL", "llama-3.1-8b-instant")
_MAX_JUDGE = 18   # keep the per-source batch small — Groq free tier is tokens-per-minute limited


def _text(it: dict) -> str:
    return str(it.get("title") or it.get("post_text") or it.get("text") or it.get("snippet") or "")[:140]


def _criterion(pl: "P.QueryPlan") -> str:
    parts = []
    if pl.sentiment == "negative":
        subj = pl.topic or pl.query
        parts.append(f"the post is a genuinely hostile, hateful or harmful COMMENT about {subj} "
                     "(an opinion/attack, NOT a neutral news headline)")
    if pl.anchor:
        parts.append(f'the post is really about "{pl.topic}" AND reflects the viewpoint or '
                     f'discussion of "{pl.anchor}"')
    return " AND ".join(parts)


async def _groq(criterion: str, texts: list[str]) -> set[int] | None:
    if not _GROQ_KEY or not texts:
        return None
    numbered = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(texts))
    sys = ("You are a strict content filter. Reply ONLY with a JSON array of the item numbers "
           "that clearly PASS the criterion. No prose, no explanation.")
    usr = f"CRITERION: {criterion}\n\nITEMS:\n{numbered}\n\nJSON array of passing item numbers:"
    try:
        async with httpx.AsyncClient(timeout=25) as client:
            r = await client.post(_GROQ_URL,
                                  headers={"Authorization": f"Bearer {_GROQ_KEY}"},
                                  json={"model": _MODEL, "temperature": 0, "max_tokens": 300,
                                        "messages": [{"role": "system", "content": sys},
                                                     {"role": "user", "content": usr}]})
            r.raise_for_status()
            content = r.json()["choices"][0]["message"]["content"]
        return {int(n) - 1 for n in re.findall(r"\d+", content)}
    except Exception:
        return None


async def refine(pl: "P.QueryPlan", items: list[dict]) -> tuple[list[dict], str]:
    """Window-filter → LLM-judge subjective dims (fallback to keyword) → sort → trim.
    Returns (items, judged_by) where judged_by is 'llm', 'keyword', or 'none'."""
    out = list(items)
    if pl.window_minutes is not None:
        out = [it for it in out if (a := P._age_min(it)) is not None and a <= pl.window_minutes]

    judged = "none"
    crit = _criterion(pl)
    if crit and out:
        cand = out[:_MAX_JUDGE]
        passed = await _groq(crit, [_text(it) for it in cand])
        if passed is not None:                       # LLM ran
            out = [it for i, it in enumerate(cand) if i in passed]
            judged = "llm"
        else:                                        # graceful fallback to keyword filters
            judged = "keyword"
            if pl.sentiment == "negative":
                out = [it for it in out if P._is_negative(it)]

    if pl.anchor:
        tt, at = P._toks(pl.topic), P._toks(pl.anchor)
        out.sort(key=lambda it: (-P._cooccur(it, tt, at),
                                 P._age_min(it) if P._age_min(it) is not None else 1e12))
    elif pl.sort == "recency":
        out.sort(key=lambda it: (P._age_min(it) if P._age_min(it) is not None else 1e12))
    elif pl.sort == "engagement":
        out.sort(key=P._engagement, reverse=True)
    return out[: pl.top_n], judged
