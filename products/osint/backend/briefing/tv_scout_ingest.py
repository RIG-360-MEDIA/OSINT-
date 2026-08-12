"""KA-style TV ingestion: Scout keyword-search -> free-transcript providers ->
youtube_clips_v2 (transcript_source='ka_scout'). Box-native (kome.ai/Piped), NO
YouTube relay — fully separate from Telangana's channel pipeline, zero ban risk.

Videos are dated to their publish date (created_at) so a weekly report's per-day
runs each pick up their day's TV. Marked source='ka_scout' so _tv_candidates
keeps it out of every other tenant's feed.
"""
from __future__ import annotations

import asyncio
import datetime as _dt
import logging

from sqlalchemy import text

logger = logging.getLogger("briefing.tv_scout")

# High-signal Karnataka search terms across the scope (figures, parties, schemes,
# issues). matched_entity is set to the term so the weekly TV share-of-voice can
# classify gov/opp; issue terms land as unattributed coverage (expected).
KA_KEYWORDS = [
    "DK Shivakumar", "Siddaramaiah", "G Parameshwara", "Priyank Kharge",
    "Karnataka cabinet", "Karnataka government", "Karnataka Congress",
    "R Ashok BJP", "HD Kumaraswamy", "BY Vijayendra", "Karnataka BJP", "JDS Karnataka",
    "MUDA case", "Valmiki corporation", "Gruha Lakshmi", "Shakti scheme Karnataka",
    "Anna Bhagya Karnataka", "Cauvery Karnataka", "Bengaluru BBMP",
    "Karnataka caste survey", "bike taxi Karnataka", "Karnataka politics",
]

_NOTAVAIL = "transcripts aren't available"


def _lang_of(text_: str) -> str:
    kn = sum(1 for c in text_ if "ಀ" <= c <= "೿")
    letters = sum(1 for c in text_ if c.isalpha()) or 1
    return "kn" if kn / letters > 0.12 else "en"


def _parse_dt(s: str):
    if not s:
        return None
    try:
        return _dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:  # noqa: BLE001
        return None


async def ingest(days_back: int = 7, per_kw: int = 10, pace: float = 1.2) -> dict:
    from backend.database import get_db
    from backend.collectors.cheap_stack.keyword_search import search_youtube
    from backend.collectors.youtube_v2.free_transcript import fetch_free_transcript

    now = _dt.datetime.now(_dt.timezone.utc)
    cutoff = now - _dt.timedelta(days=days_back)

    # 1. search -> collect unique recent videos (first keyword that found it wins)
    found: dict[str, dict] = {}
    for kw in KA_KEYWORDS:
        try:
            res = await search_youtube(kw, limit=per_kw)
        except Exception as exc:  # noqa: BLE001
            logger.warning("search %s failed: %s", kw, str(exc)[:80])
            continue
        for p in (res.posts or ()):
            vid = p.get("platform_post_id") or ""
            if not vid or vid in found:
                continue
            pub = _parse_dt(p.get("posted_at") or "")
            if pub and pub < cutoff:
                continue  # older than the window
            found[vid] = {"vid": vid, "kw": kw,
                          "title": (p.get("post_text") or p.get("title") or "")[:280],
                          "chan": p.get("author_username") or p.get("channel") or "",
                          "pub": pub or now}
        await asyncio.sleep(pace)

    # 2. skip videos already ingested
    async with get_db() as db:
        existing = {r.video_id for r in (await db.execute(text(
            "SELECT video_id FROM youtube_clips_v2 WHERE transcript_source='ka_scout'"
        ))).fetchall()}
    todo = [v for v in found.values() if v["vid"] not in existing]
    logger.info("tv_scout: %d unique recent videos, %d new to fetch", len(found), len(todo))

    # 3. fetch transcript + insert
    ins, miss = 0, 0
    for v in todo:
        try:
            ft = fetch_free_transcript(v["vid"])
        except Exception as exc:  # noqa: BLE001
            logger.warning("transcript %s failed: %s", v["vid"], str(exc)[:70])
            ft = None
        txt = (ft.text if ft else "") or ""
        if len(txt) < 200 or _NOTAVAIL in txt[:200].lower():
            miss += 1
            await asyncio.sleep(pace)
            continue
        async with get_db() as db:
            await db.execute(text("""
                INSERT INTO youtube_clips_v2
                  (video_id, video_title, channel_id, channel_name, video_url, embed_url,
                   clip_start_seconds, clip_end_seconds, matched_entity, summary,
                   transcript_segment, transcript_language, transcript_source, confidence,
                   importance, processed, substrate_status, created_at, video_published_at,
                   is_watchlisted, extraction_version)
                VALUES (:vid, :title, '', :chan,
                        'https://www.youtube.com/watch?v='||:vid,
                        'https://www.youtube.com/embed/'||:vid,
                        0, 0, :ent, '', :seg, :lang, 'ka_scout', 0.8,
                        'medium', false, 'ok', :created, :created, true, 0)
            """), {"vid": v["vid"], "title": v["title"], "chan": v["chan"],
                   "ent": v["kw"], "seg": txt[:60000], "lang": _lang_of(txt),
                   "created": v["pub"]})
            await db.commit()
        ins += 1
        await asyncio.sleep(pace)
    return {"unique": len(found), "new": len(todo), "inserted": ins, "no_transcript": miss}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    r = asyncio.run(ingest())
    print("RESULT:", r)
    print("TV_INGEST_DONE")
