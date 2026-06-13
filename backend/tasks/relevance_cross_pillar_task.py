"""relevance_cross_pillar_task.py — per-user v3 relevance for CLIPS + CUTTINGS (#9).

Mirrors the article relevance task but for youtube_clips_v2 and clippings, writing to
user_clip_relevance / user_cutting_relevance (migration 114). Uses the SAME v3 scorer via
the field adapters, so clips/cuttings rank alongside articles on the Entity page / feed.

Stage-1 v3 only (canonicalization #1 + geo word-boundary #2 + recency #3 + muting #8);
persists tier>0 items per user. Beat: every 15 min on recent items. One-shot: _backfill_all().
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from celery import shared_task
from sqlalchemy import text

from backend.nlp.relevance_scorer import compute_stage1_score_v3, adaptive_tier
from backend.nlp.relevance_adapters import (
    clip_to_article_dict, cutting_to_article_dict, CLIP_COLS, CUTTING_COLS,
)

logger = logging.getLogger(__name__)

PILLARS: dict[str, dict] = {
    "clip": dict(table="youtube_clips_v2", date_col="video_published_at", cols=CLIP_COLS,
                 adapter=clip_to_article_dict, rel_table="user_clip_relevance", fk="clip_id"),
    "cutting": dict(table="clippings", date_col="edition_date", cols=CUTTING_COLS,
                    adapter=cutting_to_article_dict, rel_table="user_cutting_relevance", fk="clipping_id"),
}


async def _load_users(db) -> list[dict]:
    rows = (await db.execute(text("""
        SELECT up.user_id::text AS uid, up.geo_primary, up.geo_secondary, up.signal_priorities, up.role_context,
          json_agg(json_build_object('canonical_name', ue.canonical_name, 'priority', ue.priority))
            FILTER (WHERE ue.canonical_name IS NOT NULL) AS ents
        FROM user_profiles up LEFT JOIN user_entities ue ON ue.user_id = up.user_id
        GROUP BY up.user_id, up.geo_primary, up.geo_secondary, up.signal_priorities, up.role_context
    """))).fetchall()
    out = []
    for r in rows:
        ents = r.ents or []
        if ents:
            out.append(dict(uid=r.uid, profile=dict(
                signal_priorities=r.signal_priorities or {}, geo_primary=r.geo_primary or "",
                geo_secondary=r.geo_secondary or [], role_context=r.role_context or ""), entities=ents))
    return out


async def _load_alias_map(db) -> dict:
    amap: dict[str, str] = {}
    try:
        rows = (await db.execute(text("SELECT canonical_name, aliases FROM entity_dictionary WHERE aliases IS NOT NULL"))).fetchall()
        import json as _json
        for canon, aliases in rows:
            if not canon:
                continue
            al = aliases
            if isinstance(al, str):
                try:
                    al = _json.loads(al)
                except Exception:  # noqa: BLE001
                    al = al.split(",")
            if isinstance(al, list):
                for a in al:
                    if a:
                        amap[str(a).strip().lower()] = canon.strip().lower()
    except Exception:  # noqa: BLE001
        pass
    return amap


def _matched_names(art: dict, user_entities: list, amap: dict) -> list[str]:
    watched = {amap.get(ue["canonical_name"].strip().lower(), ue["canonical_name"].strip().lower()) for ue in user_entities}
    out = []
    for e in art.get("entities_extracted", []) or []:
        nm = e.get("name")
        if nm and nm != "None" and amap.get(nm.strip().lower(), nm.strip().lower()) in watched:
            out.append(nm)
    return out


async def _score_pillar(pillar_key: str, limit: int, days: int) -> int:
    p = PILLARS[pillar_key]
    from backend.database import get_db
    async with get_db() as db:
        users = await _load_users(db)
        if not users:
            return 0
        amap = await _load_alias_map(db)
        cols = ", ".join(p["cols"])
        items = (await db.execute(text(
            f"SELECT {cols} FROM {p['table']} "
            f"WHERE {p['date_col']} > now() - (:d || ' days')::interval "
            f"AND jsonb_typeof(entities_extracted)='array' "
            f"ORDER BY {p['date_col']} DESC LIMIT :lim"
        ), {"d": str(days), "lim": limit})).fetchall()
        arts = [p["adapter"](dict(it._mapping)) for it in items]

        written = 0
        for u in users:
            scored = []
            for art in arts:
                s, dbg = compute_stage1_score_v3(art, u["profile"], u["entities"], [], alias_map=amap)
                if dbg.get("muted") or s <= 0:
                    continue
                scored.append((art, s))
            if not scored:
                continue
            vals = sorted(s for _, s in scored)
            p50 = vals[len(vals) // 2]
            p80 = vals[int(len(vals) * 0.8)] if len(vals) > 1 else vals[-1]
            for art, s in scored:
                tier = adaptive_tier(s, p50, p80)
                if tier == 0:
                    continue
                await db.execute(text(
                    f"INSERT INTO {p['rel_table']} (user_id, {p['fk']}, score_stage1, score_final, "
                    f"relevance_tier, matched_entity_names) VALUES (:u, :i, :s, :s, :t, :m) "
                    f"ON CONFLICT (user_id, {p['fk']}) DO UPDATE SET score_stage1=EXCLUDED.score_stage1, "
                    f"score_final=EXCLUDED.score_final, relevance_tier=EXCLUDED.relevance_tier, "
                    f"matched_entity_names=EXCLUDED.matched_entity_names, scored_at=now()"
                ), {"u": u["uid"], "i": art["id"], "s": float(s), "t": int(tier),
                    "m": _matched_names(art, u["entities"], amap)})
                written += 1
        await db.commit()
        return written


@shared_task(name="tasks.relevance.cross_pillar", bind=True, queue="relevance",
             soft_time_limit=540, time_limit=600)
def score_cross_pillar_relevance(self, limit: int = 400, days: int = 3) -> dict[str, Any]:
    async def _go():
        clips = await _score_pillar("clip", limit, days)
        cuttings = await _score_pillar("cutting", limit, days)
        return {"clip_rows": clips, "cutting_rows": cuttings}
    try:
        out = asyncio.run(_go())
        if out["clip_rows"] or out["cutting_rows"]:
            logger.info("cross_pillar relevance: %s", out)
        return out
    except Exception as exc:  # noqa: BLE001
        logger.exception("cross_pillar relevance failed: %s", exc)
        return {"error": str(exc)[:200]}


async def _score_one(pillar_key: str, item_id) -> int:
    """Score ONE clip/cutting for all users (event-driven, called from the enrich step)."""
    p = PILLARS[pillar_key]
    from backend.database import get_db
    async with get_db() as db:
        users = await _load_users(db)
        if not users:
            return 0
        amap = await _load_alias_map(db)
        cols = ", ".join(p["cols"])
        row = (await db.execute(text(
            f"SELECT {cols} FROM {p['table']} WHERE id::text = :id "
            f"AND jsonb_typeof(entities_extracted)='array'"
        ), {"id": str(item_id)})).fetchone()
        if not row:
            return 0
        art = p["adapter"](dict(row._mapping))
        written = 0
        for u in users:
            s, dbg = compute_stage1_score_v3(art, u["profile"], u["entities"], [], alias_map=amap)
            if dbg.get("muted") or s <= 0:
                continue
            tier = adaptive_tier(s)  # single item → global tiers (no per-user distribution here)
            if tier == 0:
                continue
            await db.execute(text(
                f"INSERT INTO {p['rel_table']} (user_id, {p['fk']}, score_stage1, score_final, "
                f"relevance_tier, matched_entity_names) VALUES (:u, :i, :s, :s, :t, :m) "
                f"ON CONFLICT (user_id, {p['fk']}) DO UPDATE SET score_stage1=EXCLUDED.score_stage1, "
                f"score_final=EXCLUDED.score_final, relevance_tier=EXCLUDED.relevance_tier, "
                f"matched_entity_names=EXCLUDED.matched_entity_names, scored_at=now()"
            ), {"u": u["uid"], "i": art["id"], "s": float(s), "t": int(tier),
                "m": _matched_names(art, u["entities"], amap)})
            written += 1
        await db.commit()
        return written


@shared_task(name="tasks.relevance.score_one_clip", queue="relevance", soft_time_limit=120)
def score_one_clip(clip_id) -> dict[str, Any]:
    try:
        return {"written": asyncio.run(_score_one("clip", clip_id))}
    except Exception as exc:  # noqa: BLE001
        logger.warning("score_one_clip(%s) failed: %s", clip_id, exc)
        return {"error": str(exc)[:120]}


@shared_task(name="tasks.relevance.score_one_cutting", queue="relevance", soft_time_limit=120)
def score_one_cutting(cutting_id) -> dict[str, Any]:
    try:
        return {"written": asyncio.run(_score_one("cutting", cutting_id))}
    except Exception as exc:  # noqa: BLE001
        logger.warning("score_one_cutting(%s) failed: %s", cutting_id, exc)
        return {"error": str(exc)[:120]}


async def _backfill_all(days: int = 30, batch: int = 800) -> dict[str, Any]:
    """One-shot: score all clips + cuttings from the last `days` for every user with a watchlist."""
    clips = await _score_pillar("clip", batch, days)
    cuttings = await _score_pillar("cutting", batch, days)
    print(f"cross-pillar backfill: clip_rows={clips} cutting_rows={cuttings}", flush=True)
    return {"clip_rows": clips, "cutting_rows": cuttings}
