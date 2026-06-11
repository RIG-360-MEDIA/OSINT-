"""
Celery tasks: YouTube channel discovery + transcript fetch + clip extraction.

Pipeline (all driven from Hetzner Beat — no manual laptop steps needed):

  discover_youtube_channels()  [collectors queue, every 30 min]
    RSS discovery for active channels → upserts into pending_youtube_videos.
    RSS is not IP-blocked from Hetzner datacenter IPs.

  fetch_youtube_transcripts(limit)  [youtube queue, every 3 min]
    Claims pending rows, calls fetch_transcript() which routes through
    YT_RELAY_URL (Tailscale relay on laptop) so the actual YouTube request
    comes from a residential IP. Writes transcript_json, marks 'transcribed'.
    Rate: limit=3 every 3 min ≤ 1 req/min average, well under relay 15/min cap.

  run_youtube_extraction(limit)  [youtube queue, every 5 min]
    Drains 'transcribed' rows → Groq extraction → writes youtube_clips_v2
    with substrate_status='pending' for the enrich drain.

The laptop relay (backend/collectors/youtube_v2/transcript_relay.py) must be
running for transcript fetching to work. As long as the relay is up, no other
manual step is required — the full pipeline is Beat-driven.
"""
from __future__ import annotations

import asyncio
import logging

from backend.celery_app import app

logger = logging.getLogger(__name__)


# ── Political-priority matcher ────────────────────────────────────────────────
# A pending video is "political" (top transcript priority, NEVER deprioritised or
# aged out) when its TITLE mentions a watched entity or any political term. Biased
# to HIGH RECALL: a false positive just transcribes a clip a little sooner; a false
# negative would risk missing political content, which we never accept.
_POLITICAL_KEYWORDS = frozenset({
    "revanth", "kcr", "ktr", "kt rama", "harish rao", "kishan reddy", "bhatti",
    "uttam", "owaisi", "modi", "rahul", "amit shah", "kharge", "bjp", "congress",
    "brs", "aimim", "tdp", "ysrcp", "janasena", "pawan kalyan", "chandrababu",
    "jagan", "minister", "cm ", " cm", "mla", " mp ", "assembly", "sansad",
    "parliament", "election", "poll", "party", "politics", "political", "govt",
    "government", "cabinet", "manifesto", "alliance", "opposition", "rally",
    "protest", "scheme", "telangana", "andhra", "aicc", "supreme court",
    "high court", "నేత", "ప్రభుత్వ", "ఎన్నిక", "మంత్రి", "సర్కార్",
    "नेता", "सरकार", "चुनाव", "मंत्री",
})

_terms_cache: "set[str] | None" = None


async def _load_political_terms(db) -> "set[str]":
    """Watched-entity names + political keywords, lowercased; loaded once per process."""
    global _terms_cache
    if _terms_cache is not None:
        return _terms_cache
    from sqlalchemy import text
    terms = set(_POLITICAL_KEYWORDS)
    try:
        rows = (await db.execute(text("SELECT lower(canonical_name) FROM user_entities"))).fetchall()
        for (name,) in rows:
            if not name:
                continue
            terms.add(name)
            for w in name.split():
                if len(w) > 3:
                    terms.add(w)
    except Exception:  # noqa: BLE001
        pass
    _terms_cache = terms
    return terms


def _is_political(title: "str | None", terms: "set[str]") -> bool:
    t = (title or "").lower()
    return any(term in t for term in terms)


# ── Discovery ─────────────────────────────────────────────────────────────────

@app.task(name="tasks.discover_youtube_channels", queue="collectors")
def discover_youtube_channels() -> dict:
    """RSS discovery for all active channels → upsert new videos into queue."""
    return asyncio.run(_discover())


async def _discover() -> dict:
    from sqlalchemy import text
    from backend.database import get_db
    from backend.collectors.youtube_v2.discovery import (
        discover_channel_videos, DiscoveryError,
    )

    async with get_db() as db:
        channels = (
            await db.execute(
                text(
                    "SELECT channel_id, channel_name, last_checked_at "
                    "FROM youtube_channels WHERE is_active = TRUE "
                    "ORDER BY COALESCE(last_checked_at, '1970-01-01') ASC"
                )
            )
        ).fetchall()

    if not channels:
        logger.info("discover_youtube_channels: no active channels")
        return {"channels": 0, "new_videos": 0}

    async with get_db() as _tdb:
        terms = await _load_political_terms(_tdb)

    total_new = 0
    for ch in channels:
        try:
            videos = await discover_channel_videos(
                ch.channel_id,
                since=ch.last_checked_at,
                max_results=15,
            )
        except DiscoveryError as exc:
            logger.warning("discovery failed channel=%s: %s", ch.channel_id, exc)
            continue

        inserted = 0
        async with get_db() as db:
            for v in videos:
                from datetime import datetime
                pub_dt = None
                if v.published_at:
                    try:
                        pub_dt = datetime.fromisoformat(
                            v.published_at.replace("Z", "+00:00")
                        )
                    except (ValueError, AttributeError):
                        pub_dt = None
                result = await db.execute(
                    text(
                        """
                        INSERT INTO pending_youtube_videos
                          (video_id, video_title, channel_id, channel_name,
                           video_published_at, is_political)
                        VALUES (:vid, :title, :cid, :cname, :pub, :pol)
                        ON CONFLICT (video_id) DO NOTHING
                        """
                    ),
                    {
                        "vid":   v.video_id,
                        "title": v.title[:500],
                        "cid":   v.channel_id,
                        "cname": v.channel_name[:200],
                        "pub":   pub_dt,
                        "pol":   _is_political(v.title, terms),
                    },
                )
                if result.rowcount:
                    inserted += 1
            await db.execute(
                text(
                    "UPDATE youtube_channels "
                    "SET last_checked_at = NOW() "
                    "WHERE channel_id = :cid"
                ),
                {"cid": ch.channel_id},
            )
            await db.commit()

        total_new += inserted
        logger.info(
            "discovery channel=%s (%s) found=%d new=%d",
            ch.channel_id, ch.channel_name, len(videos), inserted,
        )

    logger.info(
        "discover_youtube_channels: channels=%d total_new=%d",
        len(channels), total_new,
    )
    return {"channels": len(channels), "new_videos": total_new}


# ── Transcript fetch (via relay on laptop — residential IP hop) ───────────────

@app.task(name="tasks.fetch_youtube_transcripts", queue="youtube")
def fetch_youtube_transcripts(limit: int = 5) -> dict:
    """Drain pending videos → fetch transcripts via Tailscale relay → transcribed.

    The relay (backend/collectors/youtube_v2/transcript_relay.py) runs on the
    laptop at YT_RELAY_URL. Hetzner calls it over Tailscale so the actual
    YouTube request comes from a residential IP. No separate laptop worker needed
    as long as the relay is running.
    """
    return asyncio.run(_fetch_transcripts(limit))


async def _fetch_transcripts(limit: int) -> dict:
    import asyncio as _asyncio
    from sqlalchemy import text
    from backend.database import get_db
    from backend.collectors.youtube_v2.transcript import fetch_transcript
    from backend.collectors.youtube_v2.models import Transcript, TranscriptFailure
    import json

    _MAX_ATTEMPTS = 4

    fetched = transcribed = failed = 0
    for _ in range(max(1, limit)):
        # Claim one row atomically — same skip-locked pattern as drain_pending_clips.
        async with get_db() as db:
            row = (
                await db.execute(
                    text(
                        """
                        UPDATE pending_youtube_videos
                           SET status = 'fetching', updated_at = NOW()
                         WHERE id = (
                            SELECT id FROM pending_youtube_videos
                             WHERE status = 'pending'
                             ORDER BY is_political DESC,
                                      video_published_at DESC NULLS LAST,
                                      discovered_at DESC
                             FOR UPDATE SKIP LOCKED
                             LIMIT 1
                         )
                        RETURNING id, video_id, attempts
                        """
                    )
                )
            ).fetchone()
            await db.commit()
        if not row:
            break
        fetched += 1

        result = await _asyncio.to_thread(fetch_transcript, row.video_id)
        async with get_db() as db:
            if isinstance(result, Transcript):
                transcript_json = json.dumps({
                    "language": result.language,
                    "source":   result.source.value,
                    "segments": [
                        {"start": s.start, "duration": s.duration, "text": s.text}
                        for s in result.segments
                    ],
                })
                await db.execute(
                    text(
                        """
                        UPDATE pending_youtube_videos
                        SET status='transcribed',
                            transcript_json=CAST(:tj AS JSONB),
                            transcript_language=:lang,
                            transcript_source=:src,
                            transcribed_at=NOW(), updated_at=NOW(),
                            last_error=NULL
                        WHERE id=:id
                        """
                    ),
                    {
                        "tj":   transcript_json,
                        "lang": result.language,
                        "src":  result.source.value,
                        "id":   row.id,
                    },
                )
                transcribed += 1
                logger.info("transcript ok video=%s lang=%s segs=%d",
                            row.video_id, result.language, len(result.segments))
            else:
                failure: TranscriptFailure = result
                if failure.reason == "no_transcript":
                    await db.execute(
                        text(
                            "UPDATE pending_youtube_videos "
                            "SET status='no_transcript', updated_at=NOW(), last_error=:err "
                            "WHERE id=:id"
                        ),
                        {"err": failure.detail, "id": row.id},
                    )
                else:
                    new_attempts = row.attempts + 1
                    new_status = "failed" if new_attempts >= _MAX_ATTEMPTS else "pending"
                    await db.execute(
                        text(
                            "UPDATE pending_youtube_videos "
                            "SET attempts=:a, status=:s, last_error=:err, updated_at=NOW() "
                            "WHERE id=:id"
                        ),
                        {
                            "a":   new_attempts,
                            "s":   new_status,
                            "err": f"{failure.reason}: {failure.detail}",
                            "id":  row.id,
                        },
                    )
                failed += 1
                logger.warning("transcript %s video=%s: %s",
                               failure.reason, row.video_id, failure.detail)
            await db.commit()

    logger.info(
        "fetch_youtube_transcripts: fetched=%d transcribed=%d failed=%d",
        fetched, transcribed, failed,
    )
    return {"fetched": fetched, "transcribed": transcribed, "failed": failed}


# ── Extraction ────────────────────────────────────────────────────────────────

# Compat alias — Hetzner __init__.py (fix/brief-prod-readiness branch) imports this name
collect_youtube = discover_youtube_channels


@app.task(name="tasks.run_youtube_extraction", queue="youtube")
def run_youtube_extraction(limit: int = 10) -> dict:
    """Drain transcribed rows → run Groq extraction → write clips."""
    return asyncio.run(_extract(limit))


async def _extract(limit: int) -> dict:
    from backend.database import get_db
    from backend.collectors.youtube_v2.pipeline import run_extraction_batch

    async with get_db() as db:
        result = await run_extraction_batch(db, limit=limit)

    logger.info(
        "run_youtube_extraction: processed=%d clips_stored=%d",
        result.get("processed", 0), result.get("clips_stored", 0),
    )
    return result
