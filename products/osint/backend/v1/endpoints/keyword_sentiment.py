"""On-demand keyword sentiment (Scenario 2) for the /v1 partner API.

For an ARBITRARY keyword (not necessarily a provisioned entity), discover its
recent mentions by full-text/lexical search, live-score each with the two-field
sentiment model (stance = tone toward the keyword; impact = are events good/bad
for it), aggregate, and cache the (keyword, window) result so repeat calls are
instant.

Mirrors backend/sentiment/keyword_sentiment.py but async + on osint-backend's
own DB pool and LLM client, so it drops straight into the gateway. Discovery
matches on title+lead (the exact text scored) and windows on the indexed
collected_at; the `fts` column is name-weighted so it is only an OR fallback.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
from collections import Counter
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import text

from db import get_db
from groq_client import call_groq

from ..errors import bad_request, ok
from ..scope import ApiContext, get_context
from ..settings import DEFAULT_WINDOW_DAYS, MAX_WINDOW_DAYS

router = APIRouter(prefix="/v1", tags=["analytics"])

_FTS_CFG = os.getenv("ASKRIG_FTS_CONFIG", "simple")
_CAP = int(os.getenv("KW_SENT_CAP", "150"))          # max articles scored per call
_CONC = int(os.getenv("KW_SENT_CONC", "8"))          # concurrent LLM calls
_TTL_MIN = int(os.getenv("KW_SENT_TTL_MIN", "360"))  # cache freshness (6h)

_STANCE_W = {"positive": 1.0, "negative": -1.0, "neutral": 0.0}
_IMPACT_W = {"positive": 1.0, "negative": -1.0, "neutral": 0.0, "not_relevant": 0.0}

_SYS = (
    "You are a precise media analyst. stance = TONE toward the subject "
    "(praise/criticise/neither): positive/negative/neutral. impact = are EVENTS "
    "good/bad for the subject by CONSEQUENCES (fine/loss/arrest/expulsion=negative; "
    "win/deal/award=positive; plain mention=neutral; no stake=not_relevant). "
    'Reply ONLY JSON {"stance":"...","impact":"...","impact_confidence":0.0-1.0}.'
)

_TITLELEAD = ("coalesce(title,'') || ' ' || coalesce(lead_text_original,'') || ' ' "
              "|| coalesce(lead_text_translated,'')")

_SEARCH_SQL = text(f"""
    SELECT id::text AS id,
           coalesce(title,'') || ' — ' || coalesce(lead_text_original, lead_text_translated, '') AS body,
           published_at
    FROM articles
    WHERE collected_at > now() - make_interval(days => :days)
      AND substrate_status = 'ok' AND NOT is_duplicate
      AND ( ({_TITLELEAD}) ILIKE :pat
            OR fts @@ websearch_to_tsquery(:cfg, :q) )
    ORDER BY collected_at DESC
    LIMIT :cap
""")

_CACHE_READ_SQL = text("""
    SELECT n_matched, n_scored, capped, stance_pos, stance_neg, stance_neu,
           impact_pos, impact_neg, impact_neu, impact_nr, stance_score, impact_score,
           model, computed_at
    FROM analytics.keyword_sentiment_cache
    WHERE keyword_norm = :kw AND window_days = :days
      AND computed_at > now() - make_interval(mins => :ttl)
""")

_CACHE_WRITE_SQL = text("""
    INSERT INTO analytics.keyword_sentiment_cache
        (keyword_norm, window_days, n_matched, n_scored, capped,
         stance_pos, stance_neg, stance_neu,
         impact_pos, impact_neg, impact_neu, impact_nr,
         stance_score, impact_score, model, source, computed_at)
    VALUES (:kw, :days, :n_matched, :n_scored, :capped,
            :sp, :sn, :su, :ip, :inn, :iu, :inr, :ss, :is_, :model, 'ondemand', now())
    ON CONFLICT (keyword_norm, window_days) DO UPDATE SET
        n_matched=EXCLUDED.n_matched, n_scored=EXCLUDED.n_scored, capped=EXCLUDED.capped,
        stance_pos=EXCLUDED.stance_pos, stance_neg=EXCLUDED.stance_neg, stance_neu=EXCLUDED.stance_neu,
        impact_pos=EXCLUDED.impact_pos, impact_neg=EXCLUDED.impact_neg,
        impact_neu=EXCLUDED.impact_neu, impact_nr=EXCLUDED.impact_nr,
        stance_score=EXCLUDED.stance_score, impact_score=EXCLUDED.impact_score,
        model=EXCLUDED.model, source='ondemand', computed_at=now()
""")


def _norm(v: Any, allow_nr: bool = False) -> Optional[str]:
    s = str(v).lower()
    if allow_nr and "not" in s:
        return "not_relevant"
    if "pos" in s:
        return "positive"
    if "neg" in s:
        return "negative"
    if "neu" in s:
        return "neutral"
    return None


def _like(keyword: str) -> str:
    esc = keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{esc}%"


def _user_prompt(keyword: str, body: str) -> str:
    return f"ARTICLE:\n{body[:1500]}\n\nSUBJECT: {keyword}\n\nReturn JSON."


async def _score(keyword: str, body: str) -> Optional[tuple[str, str, Any]]:
    try:
        raw = await call_groq(
            system=_SYS, user=_user_prompt(keyword, body),
            task_type="classification", json_response=True, max_tokens_override=80,
        )
        m = re.search(r"\{.*\}", raw, re.S)
        j = json.loads(m.group(0) if m else raw)
        stance, impact = _norm(j.get("stance")), _norm(j.get("impact"), True)
        if stance and impact:
            return stance, impact, j.get("impact_confidence")
    except Exception:  # noqa: BLE001 — any failure => this article is skipped, not fatal
        return None
    return None


def _aggregate(hits: list[tuple[str, str, Any]]) -> dict[str, Any]:
    n = len(hits)
    sc = Counter(h[0] for h in hits)
    ic = Counter(h[1] for h in hits)

    def signed(counter: Counter, weights: dict[str, float]) -> Optional[float]:
        return None if not n else round(sum(weights[k] * v for k, v in counter.items()) / n, 3)

    return {
        "n_scored": n,
        "stance": {"positive": sc["positive"], "negative": sc["negative"], "neutral": sc["neutral"]},
        "impact": {"positive": ic["positive"], "negative": ic["negative"],
                   "neutral": ic["neutral"], "not_relevant": ic["not_relevant"]},
        "stance_score": signed(sc, _STANCE_W),
        "impact_score": signed(ic, _IMPACT_W),
    }


def _envelope(kw: str, days: int, *, cached: bool, n_matched: int, capped: bool,
              agg: dict[str, Any], model: str) -> dict[str, Any]:
    return {
        "keyword": kw, "window_days": days, "cached": cached,
        "n_matched": n_matched, "capped": capped, "model": model, **agg,
    }


def _cache_hit_to_envelope(kw: str, days: int, row: Any) -> dict[str, Any]:
    return {
        "keyword": kw, "window_days": days, "cached": True,
        "n_matched": row.n_matched, "n_scored": row.n_scored, "capped": row.capped,
        "stance": {"positive": row.stance_pos, "negative": row.stance_neg, "neutral": row.stance_neu},
        "impact": {"positive": row.impact_pos, "negative": row.impact_neg,
                   "neutral": row.impact_neu, "not_relevant": row.impact_nr},
        "stance_score": row.stance_score, "impact_score": row.impact_score,
        "model": row.model, "computed_at": row.computed_at.isoformat(),
    }


@router.get("/analytics/keyword-sentiment",
            summary="On-demand two-field sentiment for an arbitrary keyword")
async def keyword_sentiment(
    request: Request,
    keyword: str = Query(..., min_length=2, max_length=80,
                         description="Any word or phrase (need not be a provisioned entity)"),
    window: int = Query(DEFAULT_WINDOW_DAYS, ge=1, le=MAX_WINDOW_DAYS),
    refresh: bool = Query(False, description="Bypass the cache and recompute"),
    ctx: ApiContext = Depends(get_context),
) -> dict:
    kw = " ".join(keyword.split()).lower()
    if not kw:
        raise bad_request("'keyword' must not be empty")

    async with get_db() as db:
        if not refresh:
            cached = (await db.execute(
                _CACHE_READ_SQL, {"kw": kw, "days": window, "ttl": _TTL_MIN})).first()
            if cached is not None:
                request.state.result_count = cached.n_scored
                return ok(_cache_hit_to_envelope(kw, window, cached),
                          meta=_coverage_meta(cached.capped))

        rows = (await db.execute(_SEARCH_SQL, {
            "days": window, "pat": _like(keyword), "cfg": _FTS_CFG,
            "q": keyword, "cap": _CAP + 1})).fetchall()

    capped = len(rows) > _CAP
    rows = rows[:_CAP]
    if not rows:
        agg = _aggregate([])
        env = _envelope(kw, window, cached=False, n_matched=0, capped=False,
                        agg=agg, model="none")
        env["note"] = "no mentions of this keyword in the window"
        request.state.result_count = 0
        return ok(env, meta=_coverage_meta(False))

    sem = asyncio.Semaphore(_CONC)

    async def _bounded(body: str) -> Optional[tuple[str, str, Any]]:
        async with sem:
            return await _score(keyword, body)

    scored = await asyncio.gather(*[_bounded(r.body) for r in rows])
    hits = [s for s in scored if s]
    agg = _aggregate(hits)
    model = "groq/cerebras-two-field"

    await _write_cache_best_effort(kw, window, len(rows), capped, agg, model)

    request.state.result_count = agg["n_scored"]
    return ok(_envelope(kw, window, cached=False, n_matched=len(rows),
                        capped=capped, agg=agg, model=model),
              meta=_coverage_meta(capped))


def _coverage_meta(capped: bool) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "method": "on-demand: live-scored over the window (not precomputed)",
        "cap": _CAP,
    }
    if capped:
        meta["capped"] = True
        meta["note"] = f"more than {_CAP} matches; scored the {_CAP} most recent"
    return meta


async def _write_cache_best_effort(kw: str, days: int, n_matched: int, capped: bool,
                                   agg: dict[str, Any], model: str) -> None:
    """Persist the aggregate. Best-effort — a read-only pool must not break the call."""
    st, im = agg["stance"], agg["impact"]
    try:
        async with get_db() as db:
            await db.execute(_CACHE_WRITE_SQL, {
                "kw": kw, "days": days, "n_matched": n_matched,
                "n_scored": agg["n_scored"], "capped": capped,
                "sp": st["positive"], "sn": st["negative"], "su": st["neutral"],
                "ip": im["positive"], "inn": im["negative"], "iu": im["neutral"], "inr": im["not_relevant"],
                "ss": agg["stance_score"], "is_": agg["impact_score"], "model": model,
            })
            await db.commit()
    except Exception:  # noqa: BLE001 — caching is an optimization, never fatal
        pass
