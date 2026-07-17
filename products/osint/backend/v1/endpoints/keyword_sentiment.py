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
from .geo import _scoped_state_codes  # region-name -> Indian state_code (shared, no cycle)

router = APIRouter(prefix="/v1", tags=["analytics"])

_FTS_CFG = os.getenv("ASKRIG_FTS_CONFIG", "simple")
_CAP = int(os.getenv("KW_SENT_CAP", "60"))           # max items scored per call (kept within the client budget)
_GLOBAL_CONC = int(os.getenv("KW_SENT_GLOBAL_CONC", "10"))  # TOTAL live LLM calls in flight across ALL requests
_BUDGET_S = float(os.getenv("KW_SENT_BUDGET_S", "20"))      # per-request wall-clock budget (under the client's 25s)
_TTL_MIN = int(os.getenv("KW_SENT_TTL_MIN", "360"))  # cache freshness (6h)

# ONE process-wide semaphore bounds concurrent live LLM calls across every in-flight
# request, so N simultaneous callers can never fan out to N×conc calls and starve.
_GLOBAL_SEM = asyncio.Semaphore(_GLOBAL_CONC)


async def _score_bodies(keyword: str, bodies: list[str]) -> tuple[list, bool]:
    """Score bodies under the GLOBAL concurrency cap + a wall-clock budget. Returns
    (results aligned to `bodies`, timed_out). Anything not finished within the budget
    is cancelled and returned as None — the endpoint ALWAYS answers within the budget,
    flagging partial results rather than hanging past the client's timeout."""
    async def _one(body: str):
        async with _GLOBAL_SEM:
            return await _score(keyword, body)
    tasks = [asyncio.ensure_future(_one(b)) for b in bodies]
    if not tasks:
        return [], False
    done, pending = await asyncio.wait(tasks, timeout=_BUDGET_S)
    for t in pending:
        t.cancel()
    out = []
    for t in tasks:
        if t in done and not t.cancelled():
            try:
                out.append(t.result())
            except Exception:  # noqa: BLE001
                out.append(None)
        else:
            out.append(None)
    return out, bool(pending)

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

def _search_sql(scope_clause: str = ""):
    """Discovery SQL. `scope_clause` (optional, a FIXED fragment — values bound via
    params) constrains matches to the org's entities/region so a generic keyword
    stays on-topic. Empty => global keyword search (the dictionary-free default)."""
    return text(f"""
        SELECT id::text AS id,
               coalesce(title,'') || ' — ' || coalesce(lead_text_original, lead_text_translated, '') AS body,
               published_at
        FROM articles
        WHERE collected_at > now() - make_interval(days => :days)
          AND substrate_status = 'ok' AND NOT is_duplicate
          AND ( ({_TITLELEAD}) ILIKE :pat
                OR fts @@ websearch_to_tsquery(:cfg, :q) )
          {scope_clause}
        ORDER BY collected_at DESC
        LIMIT :cap
    """)


_SEARCH_SQL = _search_sql()  # unscoped global keyword search (cacheable across orgs)


def _search_clips_sql(scope_clause: str = ""):
    """YouTube keyword discovery — title+transcript match. Keyword-driven / on-demand
    (no store-everything scoring). Optional entity scope via clip entity-mentions."""
    # DISTINCT ON video: youtube_clips_v2 has one row per transcript SEGMENT, so a single
    # video appears many times — scoring each segment double-counts its stance. Collapse
    # to one row per video, then order by recency.
    return text(f"""
        SELECT id, body, published_at FROM (
            SELECT DISTINCT ON (COALESCE(video_url, video_title, id::text))
                   id::text AS id,
                   coalesce(video_title,'') || ' — ' || coalesce(transcript_segment, summary, '') AS body,
                   video_published_at AS published_at, created_at
              FROM youtube_clips_v2
             WHERE created_at > now() - make_interval(days => :days)
               AND (coalesce(video_title,'') || ' ' || coalesce(transcript_segment,'')) ILIKE :pat
               {scope_clause}
             ORDER BY COALESCE(video_url, video_title, id::text), created_at DESC
        ) v ORDER BY created_at DESC LIMIT :cap
    """)

_CACHE_READ_SQL = text("""
    SELECT n_matched, n_scored, capped, stance_pos, stance_neg, stance_neu,
           impact_pos, impact_neg, impact_neu, impact_nr, stance_score, impact_score,
           model, computed_at, article_ids
    FROM analytics.keyword_sentiment_cache
    WHERE keyword_norm = :kw AND window_days = :days
      AND computed_at > now() - make_interval(mins => :ttl)
""")

_CACHE_WRITE_SQL = text("""
    INSERT INTO analytics.keyword_sentiment_cache
        (keyword_norm, window_days, n_matched, n_scored, capped,
         stance_pos, stance_neg, stance_neu,
         impact_pos, impact_neg, impact_neu, impact_nr,
         stance_score, impact_score, model, source, computed_at, article_ids)
    VALUES (:kw, :days, :n_matched, :n_scored, :capped,
            :sp, :sn, :su, :ip, :inn, :iu, :inr, :ss, :is_, :model, 'ondemand', now(),
            CAST(:aids AS uuid[]))
    ON CONFLICT (keyword_norm, window_days) DO UPDATE SET
        n_matched=EXCLUDED.n_matched, n_scored=EXCLUDED.n_scored, capped=EXCLUDED.capped,
        stance_pos=EXCLUDED.stance_pos, stance_neg=EXCLUDED.stance_neg, stance_neu=EXCLUDED.stance_neu,
        impact_pos=EXCLUDED.impact_pos, impact_neg=EXCLUDED.impact_neg,
        impact_neu=EXCLUDED.impact_neu, impact_nr=EXCLUDED.impact_nr,
        stance_score=EXCLUDED.stance_score, impact_score=EXCLUDED.impact_score,
        model=EXCLUDED.model, source='ondemand', computed_at=now(),
        article_ids=EXCLUDED.article_ids
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


def _clips_to_pillar(hits: list[tuple[str, str, Any]]) -> dict[str, Any]:
    """Map live-scored clip (stance, impact, conf) tuples to the client per-pillar shape
    (supportive/neutral/critical + net_lean + impact) so YouTube slots beside the
    articles/newspaper pillars in /analytics/sentiment."""
    supportive = neutral = critical = 0
    impact = {"positive": 0, "negative": 0, "neutral": 0, "not_relevant": 0}
    for stance, imp, _ in hits:
        if stance == "positive":
            supportive += 1
        elif stance == "negative":
            critical += 1
        elif stance == "neutral":
            neutral += 1
        if imp in impact:
            impact[imp] += 1
    total = supportive + neutral + critical
    return {
        "supportive": supportive, "neutral": neutral, "critical": critical,
        "total": total,
        "net_lean": round((supportive - critical) / total, 4) if total else 0.0,
        "impact": impact,
    }


async def youtube_sentiment_for(db, keyword: str, window_days: int,
                                entity_ids: list[str] | None = None) -> dict[str, Any]:
    """Keyword-driven YouTube sentiment for `keyword` (e.g. an entity's name): discover
    matching clips (optionally entity-scoped), live two-field score them, and return the
    per-pillar shape + clip_ids for drill-down. On-demand — nothing is stored/cached."""
    clip_scope = ""
    params: dict[str, Any] = {"days": window_days, "pat": _like(keyword), "cap": _CAP + 1}
    if entity_ids:
        clip_scope = ("AND EXISTS (SELECT 1 FROM youtube_clip_entity_mentions m "
                      "WHERE m.clip_id = youtube_clips_v2.id AND m.entity_id = ANY(CAST(:s_eids AS uuid[])))")
        params["s_eids"] = list(entity_ids)
    rows = (await db.execute(_search_clips_sql(clip_scope), params)).fetchall()[:_CAP]
    if not rows:
        pillar = _clips_to_pillar([])
        pillar["clip_ids"] = []
        return pillar
    scored, _timed_out = await _score_bodies(keyword, [r.body for r in rows])
    hits = [s for s in scored if s]
    clip_ids = [r.id for r, s in zip(rows, scored) if s]
    pillar = _clips_to_pillar(hits)
    pillar["clip_ids"] = clip_ids
    return pillar


def _envelope(kw: str, days: int, *, cached: bool, n_matched: int, capped: bool,
              agg: dict[str, Any], model: str, article_ids: list[str] | None = None) -> dict[str, Any]:
    return {
        "keyword": kw, "window_days": days, "cached": cached,
        "n_matched": n_matched, "capped": capped, "model": model,
        "article_ids": article_ids or [],  # drill-down: the articles that made this number
        **agg,
    }


def _cache_hit_to_envelope(kw: str, days: int, row: Any) -> dict[str, Any]:
    return {
        "keyword": kw, "window_days": days, "cached": True,
        "n_matched": row.n_matched, "n_scored": row.n_scored, "capped": row.capped,
        "stance": {"positive": row.stance_pos, "negative": row.stance_neg, "neutral": row.stance_neu},
        "impact": {"positive": row.impact_pos, "negative": row.impact_neg,
                   "neutral": row.impact_neu, "not_relevant": row.impact_nr},
        "stance_score": row.stance_score, "impact_score": row.impact_score,
        "article_ids": [str(x) for x in (row.article_ids or [])],
        "model": row.model, "computed_at": row.computed_at.isoformat(),
    }


@router.get("/analytics/keyword-sentiment",
            summary="On-demand two-field sentiment for an arbitrary keyword")
async def keyword_sentiment(
    request: Request,
    keyword: str = Query(..., min_length=2, max_length=80,
                         description="Any word or phrase (need not be a provisioned entity)"),
    window: int | None = Query(None, ge=1, le=MAX_WINDOW_DAYS,
                               description=f"Lookback in days (default {DEFAULT_WINDOW_DAYS}, "
                                           f"max {MAX_WINDOW_DAYS}). 'days' is accepted as an alias."),
    days: int | None = Query(None, ge=1, le=MAX_WINDOW_DAYS,
                             description="Alias for 'window'."),
    refresh: bool = Query(False, description="Bypass the cache and recompute"),
    scope: bool = Query(False, description="Constrain discovery to your provisioned "
                        "entities/region (recommended for generic keywords)"),
    pillars: str = Query("articles", pattern="^(articles|clips|both)$",
                         description="Search news articles, YouTube clips, or both"),
    ctx: ApiContext = Depends(get_context),
) -> dict:
    # `days` is the name clients reach for first. FastAPI ignores unknown query
    # params, so `?days=30` used to be silently discarded and the caller got the
    # 7-day default back -- indistinguishable from "you have thin coverage".
    # Accept both; disagreement is a 400 rather than a silent winner.
    if window is not None and days is not None and window != days:
        raise bad_request("pass either 'window' or 'days', not both with different values")
    window = window if window is not None else (days if days is not None else DEFAULT_WINDOW_DAYS)

    kw = " ".join(keyword.split()).lower()
    if not kw:
        raise bad_request("'keyword' must not be empty")

    # Optional scope guard: keep a generic keyword on-topic by intersecting discovery
    # with the org's entity mentions / region districts (language-agnostic — catches
    # Telugu articles an English region-word would miss). Scoped results are org-specific,
    # so they BYPASS the global (keyword, window) cache.
    scope_clause, scope_params = "", {}
    if scope and not ctx.scope.all_entities:
        preds: list[str] = []
        if ctx.scope.entity_ids:
            preds.append("EXISTS (SELECT 1 FROM article_entity_mentions aem "
                         "WHERE aem.article_id = articles.id AND aem.entity_id = ANY(CAST(:s_eids AS uuid[])))")
            scope_params["s_eids"] = list(ctx.scope.entity_ids)
        scodes = _scoped_state_codes(ctx.scope.regions)
        if scodes:
            preds.append("EXISTS (SELECT 1 FROM article_districts ad JOIN districts d ON d.id = ad.district_id "
                         "WHERE ad.article_id = articles.id AND d.state_code = ANY(:s_scodes))")
            scope_params["s_scodes"] = scodes
        if preds:
            scope_clause = "AND (" + " OR ".join(preds) + ")"
    # clips carry no district geo, so they scope by entity mentions only.
    clip_scope = ""
    if scope and not ctx.scope.all_entities and ctx.scope.entity_ids and pillars in ("clips", "both"):
        clip_scope = ("AND EXISTS (SELECT 1 FROM youtube_clip_entity_mentions m "
                      "WHERE m.clip_id = youtube_clips_v2.id AND m.entity_id = ANY(CAST(:s_eids AS uuid[])))")
    # Only the plain (articles-only, unscoped) path uses the shared global cache.
    use_cache = not refresh and not scope_clause and pillars == "articles"

    disc: list[tuple[str, str, str]] = []  # (kind, id, body)
    async with get_db() as db:
        if use_cache:
            cached = (await db.execute(
                _CACHE_READ_SQL, {"kw": kw, "days": window, "ttl": _TTL_MIN})).first()
            if cached is not None:
                request.state.result_count = cached.n_scored
                return ok(_cache_hit_to_envelope(kw, window, cached),
                          meta=_coverage_meta(cached.capped))
        if pillars in ("articles", "both"):
            r = (await db.execute(_search_sql(scope_clause), {
                "days": window, "pat": _like(keyword), "cfg": _FTS_CFG,
                "q": keyword, "cap": _CAP + 1, **scope_params})).fetchall()
            disc += [("article", x.id, x.body) for x in r]
        if pillars in ("clips", "both"):
            cp = {"s_eids": scope_params["s_eids"]} if (clip_scope and "s_eids" in scope_params) else {}
            r = (await db.execute(_search_clips_sql(clip_scope), {
                "days": window, "pat": _like(keyword), "cap": _CAP + 1, **cp})).fetchall()
            disc += [("clip", x.id, x.body) for x in r]

    capped = len(disc) > _CAP
    disc = disc[:_CAP]
    if not disc:
        agg = _aggregate([])
        env = _envelope(kw, window, cached=False, n_matched=0, capped=False,
                        agg=agg, model="none")
        env["note"] = ("no mentions of this keyword in your scope" if scope_clause
                       else "no mentions of this keyword in the window")
        env["scoped"] = bool(scope_clause)
        env["pillars"] = pillars
        request.state.result_count = 0
        return ok(env, meta=_coverage_meta(False))

    scored, timed_out = await _score_bodies(keyword, [d[2] for d in disc])
    hits = [s for s in scored if s]
    article_ids = [d[1] for d, s in zip(disc, scored) if s and d[0] == "article"]
    clip_ids = [d[1] for d, s in zip(disc, scored) if s and d[0] == "clip"]
    agg = _aggregate(hits)
    model = "groq/cerebras-two-field"

    if not scope_clause and pillars == "articles":  # global cache = unscoped articles only
        await _write_cache_best_effort(kw, window, len(disc), capped, agg, model, article_ids)

    # Strict on-demand: authorise later transcript pulls only for clips this keyword
    # query actually surfaced to this org.
    if clip_ids:
        from .. import queries
        await queries.record_clip_grants(ctx.principal.org_id, clip_ids)

    request.state.result_count = agg["n_scored"]
    env = _envelope(kw, window, cached=False, n_matched=len(disc),
                    capped=capped, agg=agg, model=model, article_ids=article_ids)
    env["clip_ids"] = clip_ids
    env["scoped"] = bool(scope_clause)
    env["pillars"] = pillars
    env["partial"] = timed_out  # true if the wall-clock budget cut scoring short
    return ok(env, meta=_coverage_meta(capped))


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
                                   agg: dict[str, Any], model: str,
                                   article_ids: list[str] | None = None) -> None:
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
                "aids": list(article_ids or []),
            })
            await db.commit()
    except Exception:  # noqa: BLE001 — caching is an optimization, never fatal
        pass
