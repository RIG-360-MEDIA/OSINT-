"""
tasks.coverage.pick_breaking_per_user

Per-user breaking-news selection. Runs every 60 minutes.

Algorithm (clean cutover replacing the DBSCAN cluster pipeline):

  1. For each active user_profile, take all articles ingested in the
     last 60 minutes for which user_article_relevance has them in
     relevance_tier 1 or 2 AND the source's tier is 1 or 2.
  2. Strip out junk titles (horoscope / listicle / recipe patterns).
  3. Collapse near-duplicates via LaBSE cosine >= 0.92 - wire copies
     from multiple outlets count as one candidate, with the source
     count carried into near_dup_sources.
  4. Stickiness: if the user's previous pick is still in the candidate
     set, keep it (no LLM call, no row rewrite).
  5. Decision tree:
       - 0 candidates  -> keep previous (stale row remains)
       - 1 candidate   -> it wins
       - >=2 with >=1 source_tier=1 -> consider only tier-1 candidates
       - >=2 all source_tier=2      -> consider tier-2 candidates
       - within selection: 1 left -> wins; >1 -> Groq picks the
         biggest-news-for-this-user from top 10 by score_final.
  6. Upsert user_breaking_now.

Replaces backend/tasks/coverage/breaking_task.py (DBSCAN pipeline).
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

import numpy as np
from sqlalchemy import text

from backend.celery_app import app
from backend.database import get_db
from backend.nlp.groq_client import (
    FAST_MODEL,
    GroqCallFailed,
    GroqQuotaExhausted,
    call_groq,
)

logger = logging.getLogger(__name__)


_WINDOW_MINUTES = 60
_DEDUP_COSINE_THRESH = 0.92
_GROQ_INPUT_CAP = 10
_PICKER_MODEL = FAST_MODEL


_JUNK_TITLE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bhoroscope\b", re.IGNORECASE),
    re.compile(r"\brashifal\b", re.IGNORECASE),
    re.compile(r"\b(top|best)\s+\d+\b", re.IGNORECASE),
    re.compile(r"\b\d+\s+(things|ways|reasons|tips|tricks|hacks)\b", re.IGNORECASE),
    re.compile(r"\brecipe\b", re.IGNORECASE),
    re.compile(r"\bvastu\b", re.IGNORECASE),
    re.compile(r"\bnumerology\b", re.IGNORECASE),
    re.compile(r"\baaj\s+ka\b", re.IGNORECASE),
    re.compile(r"\bdaily\s+(prediction|brief)\b", re.IGNORECASE),
    re.compile(r"\bweather\s+(forecast|update)\b", re.IGNORECASE),
]


def _is_junk_title(title: str | None) -> bool:
    if not title:
        return False
    return any(p.search(title) for p in _JUNK_TITLE_PATTERNS)


_CANDIDATE_SQL = text(
    """
    SELECT
      a.id::text                              AS article_id,
      a.title                                 AS title,
      a.lead_text_translated                  AS lead_en,
      a.lead_text_original                    AS lead_native,
      a.url                                   AS url,
      a.thumbnail_url                         AS thumbnail_url,
      a.published_at                          AS published_at,
      a.collected_at                          AS collected_at,
      a.source_tier                           AS source_tier,
      a.topic_category                        AS topic_category,
      a.geo_primary                           AS geo_primary,
      a.labse_embedding                       AS embedding,
      uar.relevance_tier                      AS relevance_tier,
      uar.score_final                         AS score_final,
      s.name                                  AS source_name
    FROM user_article_relevance uar
    JOIN articles a       ON a.id = uar.article_id
    LEFT JOIN sources s   ON s.id = a.source_id
    WHERE uar.user_id     = :uid
      AND a.collected_at  > now() - make_interval(mins => :minutes)
      AND a.source_tier IN (1, 2)
      AND uar.relevance_tier IN (1, 2)
      AND COALESCE(a.is_duplicate, false) = false
    ORDER BY uar.score_final DESC NULLS LAST, a.collected_at DESC
    """
)


async def _fetch_candidates(db, user_id: str) -> list[dict[str, Any]]:
    res = await db.execute(
        _CANDIDATE_SQL,
        {"uid": user_id, "minutes": _WINDOW_MINUTES},
    )
    rows = res.mappings().all()
    out: list[dict[str, Any]] = []
    for r in rows:
        if _is_junk_title(r["title"]):
            continue
        emb = r["embedding"]
        if emb is None:
            vec = None
        elif isinstance(emb, str):
            vec = np.array(json.loads(emb), dtype=np.float32)
        else:
            vec = np.array(emb, dtype=np.float32)
        out.append({**dict(r), "vec": vec})
    return out


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def _collapse_near_duplicates(
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    clusters: list[dict[str, Any]] = []
    for cand in candidates:
        cand_vec = cand.get("vec")
        attached = False
        if cand_vec is not None:
            for c in clusters:
                rep_vec = c.get("vec")
                if rep_vec is None:
                    continue
                if _cosine(cand_vec, rep_vec) >= _DEDUP_COSINE_THRESH:
                    c["near_dup_sources"] = c.get("near_dup_sources", 1) + 1
                    attached = True
                    break
        if not attached:
            cand_copy = dict(cand)
            cand_copy["near_dup_sources"] = 1
            clusters.append(cand_copy)
    return clusters


def _geo_score(article_geo: str | None, user_geo: str | None) -> int:
    """
    Score an article's geographic relevance to the user.

      3  exact match or substring overlap (e.g. user=Hyderabad,
         article=Hyderabad / "Hyderabad, Telangana").
      2  same broad region — both Telangana / both AP / both India-state.
      1  national-level (India / National / null) — neutral fallback.
      0  international or unrelated state.
    """
    if not user_geo:
        return 1
    a = (article_geo or "").strip().lower()
    u = user_geo.strip().lower()
    if not a:
        return 1
    if a == u or a in u or u in a:
        return 3
    _STATE_NEIGHBOURS: dict[str, set[str]] = {
        "hyderabad":      {"telangana", "andhra pradesh", "secunderabad"},
        "telangana":      {"hyderabad", "andhra pradesh", "secunderabad"},
        "andhra pradesh": {"telangana", "hyderabad", "amaravati"},
    }
    nbr = _STATE_NEIGHBOURS.get(u, set())
    if any(token in a for token in nbr):
        return 2
    if a in {"india", "national", "delhi", "new delhi"}:
        return 1
    return 0


def _prerank_pool(
    pool: list[dict[str, Any]], user_geo: str | None
) -> list[dict[str, Any]]:
    """
    Sort the candidate pool by (geo_score DESC, score_final DESC) so that
    Groq sees regionally-relevant stories first regardless of how loud
    international stories sound.
    """
    return sorted(
        pool,
        key=lambda c: (
            _geo_score(c.get("geo_primary"), user_geo),
            c.get("score_final") or 0.0,
        ),
        reverse=True,
    )


async def _groq_pick_and_summarize(
    candidates: list[dict[str, Any]],
    profile: dict[str, Any],
) -> tuple[str | None, str | None, str | None, str | None, dict | None]:
    """
    Pick + summarize in one call. Returns
    (article_id, headline_one_line, why_for_user, decision_reason, raw).
    """
    top = candidates[:_GROQ_INPUT_CAP]
    body_lines: list[str] = []
    for i, c in enumerate(top, 1):
        lead = (c.get("lead_en") or c.get("lead_native") or "")[:280]
        body_lines.append(
            f"[{i}] (tier={c['source_tier']} src={c.get('source_name') or '?'} "
            f"topic={c.get('topic_category') or '?'} "
            f"geo={c.get('geo_primary') or '?'})\n"
            f"  Title: {c['title']}\n"
            f"  Lead: {lead}"
        )
    sources_block = "\n\n".join(body_lines)

    sys_prompt = (
        "You pick the single most consequential breaking-news item for a "
        "specific user, then write a short catchy English headline and a "
        "one-line explanation of why it matters to THAT user. Output "
        "STRICT JSON, no fences:\n"
        "{\"choice\": <1..N>, "
        "\"headline_one_line\": \"<max 12 words, catchy English headline of "
        "the chosen article, no quotes>\", "
        "\"why_for_user\": \"<max 22 words, plain English, concrete impact "
        "on this user given their role and geography>\", "
        "\"reason\": \"<max 14 words, why this beat the other candidates>\"}"
    )

    priorities_json = json.dumps(profile.get("signal_priorities") or {})
    user_prompt = (
        f"USER: role={profile.get('role_type')} "
        f"geo={profile.get('geo_primary')} "
        f"priorities={priorities_json}\n\n"
        "RANKING RULES (in order — locality dominates):\n"
        "  1. PREFER stories about the user's region (geo match).\n"
        "  2. THEN national stories with direct impact on the user's role.\n"
        "  3. Pick international ONLY when there is an immediate, concrete "
        "local impact, and you must state that local impact explicitly in "
        "why_for_user.\n"
        "  4. Avoid trivia, sports, celebrity, listicles.\n\n"
        "WRITING RULES:\n"
        "  - headline_one_line: catchy English, present tense, no clickbait, "
        "no all-caps, no source name.\n"
        "  - why_for_user: speak directly to the user's situation, not the "
        "story in general. Concrete (\"could raise petrol prices in "
        "Hyderabad\") not abstract (\"affects markets\").\n\n"
        f"CANDIDATES:\n{sources_block}\n\n"
        "Return only the JSON object."
    )

    try:
        raw_text = await call_groq(
            system=sys_prompt,
            user=user_prompt,
            model=_PICKER_MODEL,
            task_type="relevance_explanation",
            json_response=True,
        )
    except (GroqCallFailed, GroqQuotaExhausted) as exc:
        logger.warning("breaking-pick: groq+cerebras both failed: %s", exc)
        return None, None, None, None, None

    try:
        parsed = json.loads(raw_text)
    except (TypeError, ValueError):
        logger.warning("breaking-pick: invalid JSON from picker: %r", raw_text)
        return None, None, None, None, None

    choice = parsed.get("choice")
    if not isinstance(choice, int) or not (1 <= choice <= len(top)):
        return None, None, None, None, parsed

    headline = (parsed.get("headline_one_line") or "").strip() or None
    why = (parsed.get("why_for_user") or "").strip() or None
    decision_reason = (parsed.get("reason") or "").strip() or None

    return (
        top[choice - 1]["article_id"],
        headline,
        why,
        decision_reason,
        parsed,
    )


async def _groq_summarize_only(
    article: dict[str, Any],
    profile: dict[str, Any],
) -> tuple[str | None, str | None, dict | None]:
    """
    Summarization-only call. Used when picking is trivial (single
    candidate / single-tier-1) and we still need the catchy headline +
    why-for-user. Returns (headline, why_for_user, raw).
    """
    lead = (article.get("lead_en") or article.get("lead_native") or "")[:600]
    sys_prompt = (
        "You summarize a single news article for a specific user. Output "
        "STRICT JSON, no fences:\n"
        "{\"headline_one_line\": \"<max 12 words, catchy English headline, "
        "no quotes, no source name>\", "
        "\"why_for_user\": \"<max 22 words, plain English, concrete impact "
        "on this user given their role and geography>\"}"
    )
    user_prompt = (
        f"USER: role={profile.get('role_type')} "
        f"geo={profile.get('geo_primary')}\n\n"
        f"ARTICLE (tier={article.get('source_tier')} "
        f"src={article.get('source_name') or '?'} "
        f"topic={article.get('topic_category') or '?'} "
        f"geo={article.get('geo_primary') or '?'}):\n"
        f"  Title: {article.get('title')}\n"
        f"  Lead: {lead}\n\n"
        "Write the headline and why-for-user. why_for_user must speak "
        "directly to this user's situation, not the story in general."
    )

    try:
        raw_text = await call_groq(
            system=sys_prompt,
            user=user_prompt,
            model=_PICKER_MODEL,
            task_type="relevance_explanation",
            json_response=True,
        )
    except (GroqCallFailed, GroqQuotaExhausted) as exc:
        logger.warning("breaking-summarize: groq+cerebras failed: %s", exc)
        return None, None, None

    try:
        parsed = json.loads(raw_text)
    except (TypeError, ValueError):
        logger.warning(
            "breaking-summarize: invalid JSON from picker: %r", raw_text
        )
        return None, None, None

    headline = (parsed.get("headline_one_line") or "").strip() or None
    why = (parsed.get("why_for_user") or "").strip() or None
    return headline, why, parsed


def _select_pool(
    candidates: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], str]:
    tier1 = [c for c in candidates if c["source_tier"] == 1]
    if tier1:
        return tier1, "tier1_only"
    return [c for c in candidates if c["source_tier"] == 2], "tier2_only"


async def _pick_for_user(
    db,
    user_id: str,
    profile: dict[str, Any],
) -> dict[str, Any]:
    candidates_raw = await _fetch_candidates(db, user_id)
    if not candidates_raw:
        return {"action": "noop_no_candidates", "user_id": user_id}

    candidates = _collapse_near_duplicates(candidates_raw)
    candidate_count = len(candidates)

    prev = await db.execute(
        text("SELECT article_id::text FROM user_breaking_now WHERE user_id = :uid"),
        {"uid": user_id},
    )
    prev_row = prev.first()
    if prev_row is not None:
        prev_article_id = prev_row[0]
        if any(c["article_id"] == prev_article_id for c in candidates):
            return {
                "action": "noop_sticky",
                "user_id": user_id,
                "kept_article_id": prev_article_id,
            }

    user_geo = profile.get("geo_primary")
    headline_one_line: str | None = None
    why_for_user: str | None = None
    raw_resp: dict | None = None

    if candidate_count == 1:
        winner = candidates[0]
        decision = "single_candidate"
        reason = "Only candidate in window."
        headline_one_line, why_for_user, raw_resp = await _groq_summarize_only(
            winner, profile
        )
    else:
        pool, pool_label = _select_pool(candidates)
        if not pool:
            return {"action": "noop_empty_pool", "user_id": user_id}
        # Geographic pre-ranking: regional > national > international.
        # Pre-sorting before Groq counters the model's macro-magnitude bias.
        pool = _prerank_pool(pool, user_geo)
        if len(pool) == 1:
            winner = pool[0]
            decision = f"{pool_label}_single"
            reason = "Only candidate at the higher tier in window."
            headline_one_line, why_for_user, raw_resp = await _groq_summarize_only(
                winner, profile
            )
        else:
            (
                article_id,
                headline_one_line,
                why_for_user,
                ai_reason,
                raw_resp,
            ) = await _groq_pick_and_summarize(pool, profile)
            if article_id is None:
                # Groq failed: fall back to top-of-pool (already geo-ranked).
                winner = pool[0]
                decision = f"{pool_label}_fallback_score"
                reason = "Groq pick failed; using top geo-ranked candidate."
                headline_one_line, why_for_user, raw_resp = (
                    await _groq_summarize_only(winner, profile)
                )
            else:
                winner_match = next(
                    (c for c in pool if c["article_id"] == article_id),
                    None,
                )
                if winner_match is None:
                    return {"action": "noop_groq_unmapped", "user_id": user_id}
                winner = winner_match
                decision = f"{pool_label}_groq_pick"
                reason = ai_reason or "Selected by AI as biggest news for user."

    return {
        "action": "upsert",
        "user_id": user_id,
        "article_id": winner["article_id"],
        "source_tier": int(winner["source_tier"]),
        "relevance_tier": int(winner["relevance_tier"]),
        "candidates_count": candidate_count,
        "near_dup_sources": int(winner.get("near_dup_sources", 1)),
        "headline_one_line": headline_one_line,
        "why_for_user": why_for_user,
        "decision_path": decision,
        "reason": reason,
        "picker_model": _PICKER_MODEL if raw_resp is not None else None,
        "raw_pick_response": raw_resp,
    }


_UPSERT_SQL = text(
    """
    INSERT INTO user_breaking_now (
      user_id, article_id, selected_at, window_started_at,
      source_tier, relevance_tier, candidates_count, near_dup_sources,
      decision_path, reason, picker_model, raw_pick_response,
      headline_one_line, why_for_user
    )
    VALUES (
      :user_id, :article_id, now(),
      now() - make_interval(mins => :minutes),
      :source_tier, :relevance_tier, :candidates_count, :near_dup_sources,
      :decision_path, :reason, :picker_model, CAST(:raw_pick_response AS jsonb),
      :headline_one_line, :why_for_user
    )
    ON CONFLICT (user_id) DO UPDATE SET
      article_id        = EXCLUDED.article_id,
      selected_at       = EXCLUDED.selected_at,
      window_started_at = EXCLUDED.window_started_at,
      source_tier       = EXCLUDED.source_tier,
      relevance_tier    = EXCLUDED.relevance_tier,
      candidates_count  = EXCLUDED.candidates_count,
      near_dup_sources  = EXCLUDED.near_dup_sources,
      decision_path     = EXCLUDED.decision_path,
      reason            = EXCLUDED.reason,
      picker_model      = EXCLUDED.picker_model,
      raw_pick_response = EXCLUDED.raw_pick_response,
      headline_one_line = EXCLUDED.headline_one_line,
      why_for_user      = EXCLUDED.why_for_user
    """
)


async def _run_async() -> dict[str, Any]:
    summary: dict[str, int] = {
        "users": 0,
        "upserts": 0,
        "sticky": 0,
        "noop_no_candidates": 0,
        "errors": 0,
    }
    async with get_db() as db:
        users = (
            await db.execute(
                text(
                    "SELECT user_id, role_type, geo_primary, signal_priorities "
                    "FROM user_profiles"
                )
            )
        ).mappings().all()

        for row in users:
            summary["users"] += 1
            user_id = str(row["user_id"])
            profile = {
                "role_type": row["role_type"],
                "geo_primary": row["geo_primary"],
                "signal_priorities": row["signal_priorities"] or {},
            }
            try:
                result = await _pick_for_user(db, user_id, profile)
            except Exception:
                logger.exception("breaking-pick: failed for user=%s", user_id)
                summary["errors"] += 1
                continue

            action = result.get("action")
            if action == "upsert":
                await db.execute(
                    _UPSERT_SQL,
                    {
                        "user_id": result["user_id"],
                        "article_id": result["article_id"],
                        "minutes": _WINDOW_MINUTES,
                        "source_tier": result["source_tier"],
                        "relevance_tier": result["relevance_tier"],
                        "candidates_count": result["candidates_count"],
                        "near_dup_sources": result["near_dup_sources"],
                        "decision_path": result["decision_path"],
                        "reason": result["reason"],
                        "picker_model": result["picker_model"],
                        "raw_pick_response": (
                            json.dumps(result["raw_pick_response"])
                            if result["raw_pick_response"] is not None
                            else None
                        ),
                        "headline_one_line": result.get("headline_one_line"),
                        "why_for_user": result.get("why_for_user"),
                    },
                )
                await db.commit()
                summary["upserts"] += 1
                logger.info(
                    "breaking-pick: user=%s upserted article=%s decision=%s",
                    user_id,
                    result["article_id"],
                    result["decision_path"],
                )
            elif action == "noop_sticky":
                summary["sticky"] += 1
            elif action == "noop_no_candidates":
                summary["noop_no_candidates"] += 1
            else:
                logger.info("breaking-pick: user=%s action=%s", user_id, action)

    return summary


@app.task(name="tasks.coverage.pick_breaking_per_user")
def pick_breaking_per_user() -> dict[str, Any]:
    return asyncio.run(_run_async())
