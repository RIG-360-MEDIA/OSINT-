"""Batch pipeline: one calendar day -> judged, verified, stored briefing.items.

LIST -> FILTER (wide net) -> JUDGE (concurrent) -> VERIFY -> STORE.

Wide net keeps the aboutness decision in the prompt but drops pure national junk
before paying for it: a candidate must be from a Telangana-covering outlet AND
either be datelined to the state (geo_primary null/TG) or mention a roster
name / scheme keyword. The prompt makes the final about_government call.

TV is deduped to one item per video_id (the corpus stores segments); its body is
title + summary + concatenated transcript.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text

from db import get_db
from briefing.refdata import load_refdata
from briefing.judge import judge_item
from briefing import prompt as P
from briefing.org_config import for_org, BASE_MUTE

logger = logging.getLogger("briefing.pipeline")

IST = timezone(timedelta(hours=5, minutes=30))
CONCURRENCY = 8


# Print newspapers whose scanned e-paper editions are paywalled/IP-blocked are
# collected via their WEB editions and classified as the NEWSPAPER pillar (they
# ARE newspapers; only the scanned image is missing). The per-org marker list
# lives in org_config; matched case-insensitively as a substring of the source.
def _pillar_for(source: str, print_markers) -> str:
    s = (source or "").lower()
    return "newspaper" if any(m in s for m in print_markers) else "web"


def ist_window(cover: date) -> tuple[datetime, datetime]:
    start = datetime(cover.year, cover.month, cover.day, 0, 0, tzinfo=IST)
    return start.astimezone(timezone.utc), (start + timedelta(days=1)).astimezone(timezone.utc)


async def _news_candidates(db, w0, w1, limit, cfg):
    # Print lags a day: a report for day D needs papers of D AND D+1 (the
    # morning-after editions that report D's events). Window extended +1 day.
    # SOURCE-based geo filter (per-org config): the state's vernacular papers
    # (np_language) + named English papers (np_sources) + geo-datelined clippings.
    # Allowing geo_primary IS NULL would let national Hindi papers through (no
    # state government coverage), so a paper counts only if it's the state's
    # vernacular/named paper OR explicitly datelined to the state.
    w1b = w1 + timedelta(days=1)
    return (await db.execute(text("""
        SELECT c.id::text item_ref,
               COALESCE(ns.name, c.newspaper_source_id::text, 'newspaper') source,
               c.language lang, c.collected_at published_at, c.headline title,
               COALESCE(c.body_text_translated, c.body_text,'') body
          FROM clippings c
          LEFT JOIN newspaper_sources ns ON ns.id = c.newspaper_source_id
         WHERE c.collected_at >= :w0 AND c.collected_at < :w1b
           AND length(COALESCE(c.body_text_translated,c.body_text,'')) > 80
           AND (ns.language = :nplang
                OR ns.name = ANY(:npsources)
                OR lower(COALESCE(c.geo_primary,'')) LIKE ANY(:geolike)
                OR lower(COALESCE(c.geo_district,'')) LIKE ANY(:districtlike))
         ORDER BY c.collected_at DESC
         LIMIT :lim
    """), {"w0": w0, "w1b": w1b, "lim": limit,
           "nplang": cfg["np_language"], "npsources": cfg["np_sources"],
           "geolike": cfg["geo_like"], "districtlike": cfg["district_like"]})).fetchall()


async def _tv_candidates(db, w0, w1, limit, cfg):
    # Org separation: an org with a tv_source_tag pulls ONLY its own Scout-ingested
    # clips; a default org (Telangana) pulls everything EXCEPT any tenant tag, so
    # the two tenants' TV never cross. created_at carries the video's publish date
    # (backfilled clips are dated to the video, so daily runs pick up their day).
    from briefing.org_config import TENANT_TV_TAGS
    tv_src = cfg.get("tv_source_tag")
    if tv_src:
        src_clause = "AND v.transcript_source = :tvsrc"
    else:
        src_clause = "AND COALESCE(v.transcript_source,'') <> ALL(:tvtags)"
    return (await db.execute(text(f"""
        SELECT v.video_id item_ref, max(v.channel_name) source, max(v.transcript_language) lang,
               min(v.created_at) published_at, max(v.video_title) title,
               max(v.video_title)||'. '||COALESCE(max(v.summary),'')||' '||
                 string_agg(COALESCE(v.transcript_segment,''), ' ') body
          FROM youtube_clips_v2 v
         WHERE v.created_at >= :w0 AND v.created_at < :w1 {src_clause}
         GROUP BY v.video_id
        HAVING length(max(v.video_title)||' '||COALESCE(max(v.summary),'')) > 40
         ORDER BY min(v.created_at) DESC
         LIMIT :lim
    """), {"w0": w0, "w1": w1, "lim": limit, "tvsrc": tv_src,
           "tvtags": list(TENANT_TV_TAGS)})).fetchall()


def _muted(title: str, body: str, mutes) -> bool:
    t = (" " + (title or "").lower() + " " + (body or "")[:200].lower() + " ")
    return any(m in t for m in mutes)


def _mnames_sql(refdata: dict[str, Any]) -> tuple[str, dict]:
    """Build an OR of ILIKE checks over title+body for roster names + scheme names."""
    names = set()
    for m in refdata["match_names"]:
        if len(m["name"]) >= 4:
            names.add(m["name"])
    for sd in refdata["scheme_defs"]:
        for v in sd["variants"] + sd["telugu"]:
            if len(v) >= 4:
                names.add(v)
    names = list(names)[:120]
    if not names:
        return "false", {}
    parts, params = [], {}
    for i, nm in enumerate(names):
        params[f"mn{i}"] = f"%{nm.lower()}%"
        parts.append(f"lower(a.title||' '||COALESCE(a.full_text_translated,a.full_text_scraped,a.lead_text_original,'')) LIKE :mn{i}")
    return "(" + " OR ".join(parts) + ")", params


async def run_day(org_id: str, cover: date, limit_per_pillar: int = 5000,
                  concurrency: int = CONCURRENCY) -> dict[str, Any]:
    w0, w1 = ist_window(cover)
    cfg = for_org(org_id)
    mutes = BASE_MUTE + cfg.get("mute_extra", [])
    async with get_db() as db:
        refdata = await load_refdata(db, org_id)
        system = P.build_system(refdata)
        mnames_sql, mparams = _mnames_sql(refdata)

        # run row
        run_id = (await db.execute(text("""
            INSERT INTO briefing.runs (org_id, cover_date, window_start, window_end, model, prompt_version, status)
            VALUES (CAST(:o AS uuid), :d, :w0, :w1, :m, :pv, 'running')
            ON CONFLICT (org_id, cover_date) DO UPDATE SET status='running', created_at=now()
            RETURNING id
        """), {"o": org_id, "d": cover, "w0": w0, "w1": w1,
               "m": "llama-3.3-70b-versatile", "pv": P.PROMPT_VERSION})).scalar()
        # NOTE: no DELETE — the unique (run_id,pillar,item_ref) + upsert lets a
        # re-run RESUME, skipping already-judged items. Essential under free-tier
        # LLM budget where a full day is judged in chunks across rate-limit windows.
        await db.commit()

        web = (await db.execute(text(f"""
                SELECT a.id::text item_ref, s.name source, a.language_iso lang, a.collected_at published_at, a.title,
                       COALESCE(a.full_text_translated, a.full_text_scraped, a.lead_text_original,'') body
                  FROM articles a JOIN sources s ON s.id=a.source_id
                 WHERE s.geo_states && CAST(:geostates AS text[])
                   AND a.collected_at >= :w0 AND a.collected_at < :w1
                   AND length(COALESCE(a.full_text_translated,a.full_text_scraped,a.lead_text_original,'')) > 120
                   AND (a.geo_primary IS NULL OR lower(a.geo_primary) LIKE ANY(:geolike) OR {mnames_sql})
                 ORDER BY a.collected_at DESC LIMIT :lim
              """), {"w0": w0, "w1": w1, "lim": limit_per_pillar,
                     "geostates": cfg["geo_states"], "geolike": cfg["geo_like"], **mparams})).fetchall()
        news = await _news_candidates(db, w0, w1, limit_per_pillar, cfg)
        tv = await _tv_candidates(db, w0, w1, limit_per_pillar, cfg)

        candidates = ([(_pillar_for(r.source, cfg["print_markers"]), r) for r in web] +
                      [("newspaper", r) for r in news] + [("tv", r) for r in tv])
        candidates = [(p, r) for p, r in candidates if not _muted(r.title, r.body, mutes)]
        # resume: skip candidates already judged for this run
        done = {(row.pillar, row.item_ref) for row in (await db.execute(text(
            "SELECT pillar, item_ref FROM briefing.items WHERE run_id=:r"), {"r": run_id})).fetchall()}
        candidates = [(p, r) for p, r in candidates if (p, r.item_ref) not in done]
        logger.info("run_day %s: web=%d news=%d tv=%d -> %d candidates",
                    cover, len(web), len(news), len(tv), len(candidates))

        sem = asyncio.Semaphore(concurrency)
        results: list[tuple[str, Any, dict]] = []

        async def work(pillar, r):
            async with sem:
                item = {"source": r.source, "medium": pillar, "lang": r.lang,
                        "published_at": str(r.published_at)[:16], "title": r.title, "body": r.body}
                v = await judge_item(item, refdata, system=system)
                results.append((pillar, r, v))
                # store INCREMENTALLY so a rate-limited / interrupted run still
                # persists everything judged so far (own short session per write).
                try:
                    async with get_db() as dbw:
                        await _store_one(dbw, org_id, run_id, pillar, r, v)
                        await dbw.commit()
                except Exception as exc:  # noqa: BLE001
                    logger.warning("store failed for %s: %s", r.item_ref, str(exc)[:120])

        await asyncio.gather(*[work(p, r) for p, r in candidates])

        counts = _tally(results)
        async with get_db() as db2:
            await db2.execute(text("""
                UPDATE briefing.runs SET status='judged', counts=CAST(:c AS jsonb) WHERE id=:r
            """), {"c": _json(counts), "r": run_id})
            await db2.commit()
        return {"run_id": str(run_id), "candidates": len(candidates), **counts}


async def _store_one(db, org_id, run_id, pillar, r, v):
    await db.execute(text("""
        INSERT INTO briefing.items
          (org_id, run_id, pillar, item_ref, source_ref, published_at, lang,
           about_government, verdict, strength, topic, department, scheme,
           event_action, event_actors, event_date, event_place, evidence,
           evidence_verified, lands_on, confidence, unclear, model, prompt_version)
        VALUES (CAST(:o AS uuid), :run, :pillar, :ref, :src, :pub, :lang,
           :about, :verdict, :strength, :topic, :dept, :scheme,
           :eaction, :eactors, :edate, :eplace, :evidence,
           :everified, :lands, :conf, :unclear, :model, :pv)
        ON CONFLICT (run_id, pillar, item_ref) DO NOTHING
    """), {"o": org_id, "run": run_id, "pillar": pillar, "ref": r.item_ref,
           "src": r.source, "pub": r.published_at, "lang": r.lang,
           "about": v["about_government"], "verdict": v["verdict"],
           "strength": v["strength"], "topic": v["topic"], "dept": v["department"],
           "scheme": v["scheme"], "eaction": v["event_action"],
           "eactors": v["event_actors"], "edate": _safe_date(v["event_date"]),
           "eplace": v["event_place"], "evidence": v["evidence"],
           "everified": v["evidence_verified"], "lands": v["lands_on"],
           "conf": v["confidence"], "unclear": v["unclear"],
           "model": v["model"], "pv": v["prompt_version"]})


def _safe_date(d):
    if not d:
        return None
    try:
        return datetime.strptime(str(d)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _tally(results) -> dict[str, int]:
    about = [v for _, _, v in results if v["about_government"] and not v["unclear"]]
    return {
        "total": len(results),
        "about_government": len(about),
        "favourable": sum(1 for v in about if v["verdict"] == "favourable"),
        "critical": sum(1 for v in about if v["verdict"] == "critical"),
        "neutral": sum(1 for v in about if v["verdict"] == "neutral"),
        "unclear": sum(1 for _, _, v in results if v["unclear"]),
    }


def _json(d) -> str:
    import json
    return json.dumps(d)
