"""LLM judge — sharpens the SUBJECTIVE dimensions keyword filters can't:
  - sentiment: is this genuinely a hostile/hateful/harmful COMMENT about the subject (not news)?
  - perspective: is this really about the topic AND reflecting the anchor's viewpoint?

Multi-backend, best-effort: try the local **Ollama pool** first (free, no daily limit), then
**Groq** (fast, but the shared org's tokens-per-day is often exhausted by the main platform).
ALWAYS degrades gracefully to the keyword filter (the floor) when both are unreachable, and
tags the result "judged by ollama|groq|keyword" so it's transparent which one actually ran.
"""
from __future__ import annotations

import asyncio
import os
import re

import httpx

import products.scout.plan as P

_GROQ_KEY = (os.environ.get("GROQ_API_KEYS", "") or os.environ.get("GROQ_API_KEY", "")).split(",")[0].strip()
_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
_GROQ_MODEL = os.environ.get("SCOUT_JUDGE_MODEL", "llama-3.1-8b-instant")
# "url|model,url|model" — prefer the smaller/faster node first.
_OLLAMA_EPS = [tuple(p.split("|", 1)) for p in os.environ.get("OLLAMA_ENDPOINTS", "").split(",")
               if "|" in p]
_OLLAMA_EPS.sort(key=lambda um: 0 if "14b" in um[1] or "7b" in um[1] else 1)
_MAX_JUDGE = 18
_SEM = asyncio.Semaphore(2)

_SYS = ("You are a strict content filter. Reply ONLY with a JSON array of the item numbers that "
        "clearly PASS the criterion, e.g. [1,3]. No prose.")


def _text(it: dict) -> str:
    return str(it.get("title") or it.get("post_text") or it.get("text") or it.get("snippet") or "")[:140]


def _criterion(pl: "P.QueryPlan") -> str:
    parts = []
    if pl.sentiment == "negative":
        subj = pl.topic or pl.query
        parts.append(f"the post is NEGATIVE toward {subj} in ANY way — criticism, hostility, an "
                     f"attack, an accusation, controversy, or a damaging/harmful/critical claim about "
                     f"{subj}. INCLUDE critical news and negative opinions. Exclude ONLY clearly "
                     "neutral-factual, positive, or promotional posts")
    if pl.anchor:
        parts.append(f'the post is really about "{pl.topic}" AND reflects the viewpoint or '
                     f'discussion of "{pl.anchor}"')
    return " AND ".join(parts)


def _prompt(criterion: str, texts: list[str]) -> str:
    numbered = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(texts))
    return f"CRITERION: {criterion}\n\nITEMS:\n{numbered}\n\nJSON array of passing item numbers:"


def _parse(content: str) -> set[int]:
    m = re.search(r"\[[\d,\s]*\]", content or "")
    return {int(n) - 1 for n in re.findall(r"\d+", m.group(0) if m else "")}


async def _ollama(criterion: str, texts: list[str]) -> set[int] | None:
    for url, model in _OLLAMA_EPS:
        try:
            async with httpx.AsyncClient(timeout=45) as c:
                r = await c.post(f"{url.strip()}/api/chat", json={
                    "model": model.strip(), "stream": False,
                    "options": {"temperature": 0, "num_predict": 200},
                    "messages": [{"role": "system", "content": _SYS},
                                 {"role": "user", "content": _prompt(criterion, texts)}]})
                r.raise_for_status()
                return _parse(r.json()["message"]["content"])
        except Exception:
            continue
    return None


async def _groq(criterion: str, texts: list[str]) -> set[int] | None:
    if not _GROQ_KEY:
        return None
    payload = {"model": _GROQ_MODEL, "temperature": 0, "max_tokens": 300,
               "messages": [{"role": "system", "content": _SYS},
                            {"role": "user", "content": _prompt(criterion, texts)}]}
    for attempt in range(2):
        try:
            async with httpx.AsyncClient(timeout=25) as c:
                r = await c.post(_GROQ_URL, headers={"Authorization": f"Bearer {_GROQ_KEY}"}, json=payload)
                if r.status_code == 429:
                    return None                          # daily/rate limit — let caller fall back
                r.raise_for_status()
                return _parse(r.json()["choices"][0]["message"]["content"])
        except Exception:
            if attempt == 0:
                await asyncio.sleep(1.0)
                continue
            return None
    return None


async def _judge(criterion: str, texts: list[str]) -> tuple[set[int] | None, str]:
    async with _SEM:
        r = await _ollama(criterion, texts)
        if r is not None:
            return r, "ollama"
        r = await _groq(criterion, texts)
        if r is not None:
            return r, "groq"
    return None, "keyword"


async def refine(pl: "P.QueryPlan", items: list[dict]) -> tuple[list[dict], str]:
    """Window-filter → LLM-judge subjective dims (fallback to keyword) → sort → trim."""
    out = list(items)
    if pl.window_minutes is not None:
        out = [it for it in out if (a := P._age_min(it)) is not None and a <= pl.window_minutes]

    judged = "none"
    crit = _criterion(pl)
    if crit and out:
        cand = out[:_MAX_JUDGE]
        passed, judged = await _judge(crit, [_text(it) for it in cand])
        if passed is not None:
            out = [it for i, it in enumerate(cand) if i in passed]
        elif pl.sentiment == "negative":                 # keyword fallback
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
