"""
THE NEWSROOM router — 9 endpoints + 1 SSE stream serving the
five-mode /clips redesign.

All routes are gated by ``Depends(require_page("clips"))`` because the
URL stays at /clips; we reuse the existing page-access slug rather than
introducing a new one (would require a migration to KNOWN_PAGES).

Routes:
  GET /api/newsroom/channels                 — registered channels
  GET /api/newsroom/wall                     — latest 5 segs/live channel
  GET /api/newsroom/stream?cursor=&entity=&lang=&limit=
  GET /api/newsroom/echo?entity_id=&hours=24
  GET /api/newsroom/dossier?entity_id=&days=7
  GET /api/newsroom/brief?date=YYYY-MM-DD
  GET /api/newsroom/breaking
  GET /api/newsroom/segments/{segment_id}
  GET /api/newsroom/stream/live              — SSE, LISTEN/NOTIFY backed
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from datetime import date, datetime, timedelta, timezone
from typing import AsyncIterator, Optional

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import text

from backend.auth.auth_middleware import require_page
from backend.database import get_db

logger = logging.getLogger(__name__)

newsroom_router = APIRouter(prefix="/api/newsroom", tags=["newsroom"])


_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_UUID_RE = re.compile(r"^[0-9a-fA-F-]{36}$")
_STREAM_DEFAULT_LIMIT = 50
_STREAM_MAX_LIMIT = 200


# ─── /me/entities — watched entities for the calling user ────────────────


@newsroom_router.get("/me/entities")
async def my_watched_entities(
    user: dict = Depends(require_page("clips")),
) -> dict:
    """Return the calling user's watched entities, joined with
    entity_dictionary so we get the canonical UUID needed by the
    /echo and /dossier routes (those expect entity_id, not name)."""
    async with get_db() as db:
        rows = await db.execute(
            text(
                """
                SELECT ed.id::text   AS id,
                       ue.canonical_name AS name,
                       ue.entity_type    AS type,
                       ue.priority
                  FROM user_entities ue
             LEFT JOIN entity_dictionary ed ON ed.canonical_name = ue.canonical_name
                 WHERE ue.user_id = CAST(:uid AS uuid)
                   AND ed.id IS NOT NULL
                 ORDER BY ue.priority DESC NULLS LAST, ue.canonical_name
                """
            ),
            {"uid": user["id"]},
        )
        return {"entities": [dict(r._mapping) for r in rows.fetchall()]}


# ─── /channels ─────────────────────────────────────────────────────────────


@newsroom_router.get("/channels")
async def list_channels(
    user: dict = Depends(require_page("clips")),
    only_active: bool = Query(default=True),
) -> dict:
    """List newsroom channels."""
    where = "WHERE active = TRUE" if only_active else ""
    async with get_db() as db:
        rows = await db.execute(
            text(
                f"""
                SELECT id::text, name, yt_handle, language, beat,
                       is_live_24x7, active, created_at
                  FROM newsroom_channels
                  {where}
                 ORDER BY name
                """
            )
        )
        return {"channels": [dict(r._mapping) for r in rows.fetchall()]}


# ─── /wall ─────────────────────────────────────────────────────────────────


@newsroom_router.get("/wall")
async def wall(
    user: dict = Depends(require_page("clips")),
    per_channel: int = Query(default=5, ge=1, le=20),
) -> dict:
    """Latest segments per active channel — drives WALL mode tiles.

    Returns one tile per active channel REGARDLESS of whether the channel
    currently has segments. Channels with no segments get a tile with
    `segments: []`, so the UI can render empty placeholders rather than
    hiding the channel entirely. Segments are joined with a 24h recency
    window so very-old VOD ingestion doesn't pollute the live feel.
    """
    async with get_db() as db:
        # Step 1 — every active channel, in deterministic order.
        chan_rows = await db.execute(
            text(
                """
                SELECT id::text      AS channel_id,
                       name          AS channel_name,
                       language,
                       beat,
                       is_live_24x7
                  FROM newsroom_channels
                 WHERE active = TRUE
                 ORDER BY is_live_24x7 DESC, name
                """
            )
        )
        channels = [dict(r._mapping) for r in chan_rows.fetchall()]

        # Step 2 — top-N latest segments per channel within 24h.
        seg_rows = await db.execute(
            text(
                """
                WITH ranked AS (
                    SELECT s.id::text         AS segment_id,
                           s.text_native, s.text_en, s.confidence,
                           s.is_quote, s.is_editorial, s.framing,
                           s.start_sec, s.end_sec, s.created_at,
                           c.id::text         AS channel_id,
                           ROW_NUMBER() OVER (
                               PARTITION BY c.id
                               ORDER BY s.created_at DESC
                           ) AS rn
                      FROM newsroom_segments s
                      JOIN newsroom_broadcasts b  ON b.id = s.broadcast_id
                      JOIN newsroom_channels c    ON c.id = b.channel_id
                     WHERE c.active = TRUE
                       AND s.created_at > NOW() - INTERVAL '24 hours'
                )
                SELECT * FROM ranked
                 WHERE rn <= :n
                 ORDER BY channel_id, created_at DESC
                """
            ),
            {"n": per_channel},
        )
        seg_by_channel: dict[str, list[dict]] = {}
        for r in seg_rows.fetchall():
            d = dict(r._mapping)
            cid = d.pop("channel_id")
            d.pop("rn", None)
            seg_by_channel.setdefault(cid, []).append(d)

    tiles = []
    for c in channels:
        tiles.append({
            "channel_id":   c["channel_id"],
            "channel_name": c["channel_name"],
            "language":     c["language"],
            "beat":         c["beat"],
            "is_live_24x7": c["is_live_24x7"],
            "segments":     seg_by_channel.get(c["channel_id"], []),
        })
    return {"tiles": tiles}


# ─── /stream (cursor-paginated) ────────────────────────────────────────────


@newsroom_router.get("/stream")
async def stream(
    user: dict = Depends(require_page("clips")),
    cursor: Optional[str] = Query(default=None, description="ISO timestamp; segments older than this"),
    entity_id: Optional[str] = Query(default=None),
    lang: Optional[str] = Query(default=None),
    limit: int = Query(default=_STREAM_DEFAULT_LIMIT, ge=1, le=_STREAM_MAX_LIMIT),
) -> dict:
    """Cursor-paginated chronological feed."""
    if cursor:
        try:
            cursor_dt = datetime.fromisoformat(cursor.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=422, detail="cursor must be ISO 8601")
    else:
        cursor_dt = None
    if entity_id and not _UUID_RE.match(entity_id):
        raise HTTPException(status_code=422, detail="entity_id must be a UUID")

    where = []
    params: dict = {"limit": limit}
    if cursor_dt:
        where.append("s.created_at < :cursor_dt")
        params["cursor_dt"] = cursor_dt
    if entity_id:
        where.append(
            "EXISTS (SELECT 1 FROM newsroom_entity_mentions em "
            "WHERE em.segment_id = s.id AND em.entity_id = :entity_id)"
        )
        params["entity_id"] = entity_id
    if lang:
        where.append("c.language = :lang")
        params["lang"] = lang

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    async with get_db() as db:
        rows = await db.execute(
            text(
                f"""
                SELECT s.id::text         AS segment_id,
                       s.text_native, s.text_en, s.confidence,
                       s.is_quote, s.is_editorial, s.framing, s.sentiment,
                       s.start_sec, s.end_sec, s.created_at, s.is_live,
                       c.id::text         AS channel_id,
                       c.name             AS channel_name,
                       c.language
                  FROM newsroom_segments s
                  JOIN newsroom_broadcasts b ON b.id = s.broadcast_id
                  JOIN newsroom_channels c   ON c.id = b.channel_id
                  {where_sql}
                 ORDER BY s.created_at DESC
                 LIMIT :limit
                """
            ),
            params,
        )
        rs = [dict(r._mapping) for r in rows.fetchall()]
    next_cursor = rs[-1]["created_at"].isoformat() if rs else None
    return {"items": rs, "next_cursor": next_cursor}


# ─── /echo ─────────────────────────────────────────────────────────────────


@newsroom_router.get("/echo")
async def echo(
    user: dict = Depends(require_page("clips")),
    entity_id: str = Query(..., description="UUID of the watched entity"),
    hours: int = Query(default=24, ge=1, le=168),
) -> dict:
    """Quotes / mentions of one entity in the last N hours."""
    if not _UUID_RE.match(entity_id):
        raise HTTPException(status_code=422, detail="entity_id must be a UUID")
    async with get_db() as db:
        rows = await db.execute(
            text(
                """
                SELECT s.id::text         AS segment_id,
                       s.text_native, s.text_en,
                       s.is_quote, s.is_editorial, s.framing, s.sentiment,
                       s.confidence, s.created_at,
                       s.speaker_label,
                       s.speaker_entity_id::text,
                       c.id::text         AS channel_id,
                       c.name             AS channel_name,
                       c.language,
                       em.was_phonetic
                  FROM newsroom_entity_mentions em
                  JOIN newsroom_segments s    ON s.id = em.segment_id
                  JOIN newsroom_broadcasts b  ON b.id = s.broadcast_id
                  JOIN newsroom_channels c    ON c.id = b.channel_id
                 WHERE em.entity_id = :entity_id
                   AND s.created_at > NOW() - make_interval(hours => :hours)
                 ORDER BY s.created_at DESC
                 LIMIT 200
                """
            ),
            {"entity_id": entity_id, "hours": hours},
        )
        rs = [dict(r._mapping) for r in rows.fetchall()]

    cross_channel_count = len({r["channel_id"] for r in rs})
    return {
        "entity_id":           entity_id,
        "hours":               hours,
        "total_mentions":      len(rs),
        "cross_channel_count": cross_channel_count,
        "items":               rs,
    }


# ─── /dossier ──────────────────────────────────────────────────────────────


@newsroom_router.get("/dossier")
async def dossier(
    user: dict = Depends(require_page("clips")),
    entity_id: str = Query(...),
    days: int = Query(default=7, ge=1, le=30),
) -> dict:
    """Mention deltas, sentiment trend, top quotes/channels for one entity."""
    if not _UUID_RE.match(entity_id):
        raise HTTPException(status_code=422, detail="entity_id must be a UUID")
    async with get_db() as db:
        # Delta: this period vs the previous one of equal length
        result = await db.execute(
            text(
                """
                SELECT
                  COUNT(*) FILTER (
                      WHERE s.created_at > NOW() - make_interval(days => :d)
                  ) AS this_period,
                  COUNT(*) FILTER (
                      WHERE s.created_at > NOW() - make_interval(days => :d2)
                        AND s.created_at <= NOW() - make_interval(days => :d)
                  ) AS prev_period,
                  AVG(s.sentiment) FILTER (
                      WHERE s.created_at > NOW() - make_interval(days => :d)
                  ) AS sentiment_avg
                  FROM newsroom_entity_mentions em
                  JOIN newsroom_segments s ON s.id = em.segment_id
                 WHERE em.entity_id = :entity_id
                """
            ),
            {"entity_id": entity_id, "d": days, "d2": days * 2},
        )
        agg = dict(result.fetchone()._mapping)

        # Top quotes
        quote_rows = await db.execute(
            text(
                """
                SELECT s.id::text AS segment_id, s.text_native, s.text_en,
                       s.framing, s.sentiment, s.created_at,
                       c.name AS channel_name
                  FROM newsroom_entity_mentions em
                  JOIN newsroom_segments s   ON s.id = em.segment_id
                  JOIN newsroom_broadcasts b ON b.id = s.broadcast_id
                  JOIN newsroom_channels c   ON c.id = b.channel_id
                 WHERE em.entity_id = :entity_id
                   AND s.is_quote = TRUE
                   AND s.created_at > NOW() - make_interval(days => :d)
                 ORDER BY s.created_at DESC
                 LIMIT 10
                """
            ),
            {"entity_id": entity_id, "d": days},
        )
        top_quotes = [dict(r._mapping) for r in quote_rows.fetchall()]

        # Top channels carrying
        chan_rows = await db.execute(
            text(
                """
                SELECT c.name AS channel_name, COUNT(*) AS n
                  FROM newsroom_entity_mentions em
                  JOIN newsroom_segments s   ON s.id = em.segment_id
                  JOIN newsroom_broadcasts b ON b.id = s.broadcast_id
                  JOIN newsroom_channels c   ON c.id = b.channel_id
                 WHERE em.entity_id = :entity_id
                   AND s.created_at > NOW() - make_interval(days => :d)
                 GROUP BY c.name
                 ORDER BY n DESC
                 LIMIT 10
                """
            ),
            {"entity_id": entity_id, "d": days},
        )
        top_channels = [dict(r._mapping) for r in chan_rows.fetchall()]

    delta_pct = None
    if agg.get("prev_period") and int(agg["prev_period"]) > 0:
        delta_pct = (
            (int(agg["this_period"] or 0) - int(agg["prev_period"]))
            / int(agg["prev_period"])
        ) * 100.0

    return {
        "entity_id":   entity_id,
        "days":        days,
        "this_period": int(agg.get("this_period") or 0),
        "prev_period": int(agg.get("prev_period") or 0),
        "delta_pct":   delta_pct,
        "sentiment_avg": float(agg["sentiment_avg"]) if agg.get("sentiment_avg") is not None else None,
        "top_quotes":  top_quotes,
        "top_channels": top_channels,
    }


# ─── /brief ────────────────────────────────────────────────────────────────


@newsroom_router.get("/brief")
async def get_brief(
    user: dict = Depends(require_page("clips")),
    date_str: Optional[str] = Query(default=None, alias="date"),
) -> dict:
    """Get the daily NEWSROOM digest. Defaults to today (IST)."""
    if date_str and not _DATE_RE.match(date_str):
        raise HTTPException(status_code=422, detail="date must be YYYY-MM-DD")

    async with get_db() as db:
        if date_str:
            target = date.fromisoformat(date_str)
            row = await db.execute(
                text(
                    """
                    SELECT id::text, for_date, generated_at, stories,
                           story_count, source_channel_count, source_segment_count
                      FROM newsroom_briefs
                     WHERE for_date = :d
                    """
                ),
                {"d": target},
            )
        else:
            row = await db.execute(
                text(
                    """
                    SELECT id::text, for_date, generated_at, stories,
                           story_count, source_channel_count, source_segment_count
                      FROM newsroom_briefs
                     ORDER BY for_date DESC
                     LIMIT 1
                    """
                )
            )
        rec = row.fetchone()
    if not rec:
        raise HTTPException(status_code=404, detail="brief not yet generated")
    return dict(rec._mapping)


# ─── /breaking ─────────────────────────────────────────────────────────────


@newsroom_router.get("/breaking")
async def breaking(
    user: dict = Depends(require_page("clips")),
    hours: int = Query(default=4, ge=1, le=24),
) -> dict:
    """Active breaking clusters in the last N hours."""
    async with get_db() as db:
        rows = await db.execute(
            text(
                """
                SELECT id::text, headline, headline_en,
                       first_seen_at, last_seen_at,
                       channel_count, segment_count,
                       severity, created_at
                  FROM newsroom_breaking_clusters
                 WHERE is_real_event = TRUE
                   AND last_seen_at > NOW() - make_interval(hours => :h)
                 ORDER BY severity DESC, last_seen_at DESC
                """
            ),
            {"h": hours},
        )
        return {"clusters": [dict(r._mapping) for r in rows.fetchall()]}


# ─── /segments/{id} ───────────────────────────────────────────────────────


@newsroom_router.get("/segments/{segment_id}")
async def segment_detail(
    segment_id: str = Path(..., regex=_UUID_RE.pattern),
    user: dict = Depends(require_page("clips")),
) -> dict:
    """Full audit detail for one segment — all 3 lens texts retained."""
    async with get_db() as db:
        rows = await db.execute(
            text(
                """
                SELECT s.id::text, s.broadcast_id::text,
                       s.start_sec, s.end_sec,
                       s.speaker_label, s.speaker_entity_id::text,
                       s.text_native, s.text_en, s.confidence,
                       s.l1_text, s.l2_text, s.l3_text,
                       s.is_quote, s.is_editorial, s.sentiment, s.framing,
                       s.is_live, s.created_at,
                       b.yt_video_id, b.title,
                       c.name AS channel_name, c.language
                  FROM newsroom_segments s
                  JOIN newsroom_broadcasts b ON b.id = s.broadcast_id
                  JOIN newsroom_channels c   ON c.id = b.channel_id
                 WHERE s.id = :sid
                """
            ),
            {"sid": segment_id},
        )
        rec = rows.fetchone()
    if not rec:
        raise HTTPException(status_code=404, detail="segment not found")
    return dict(rec._mapping)


# ─── /stream/live (SSE) ───────────────────────────────────────────────────


def _async_pg_dsn() -> str:
    return os.environ.get(
        "DATABASE_URL_SYNC",
        "postgresql://rig:rigpassword@rig-postgres:5432/rig",
    ).replace("postgresql+asyncpg", "postgresql")


@newsroom_router.get("/stream/live")
async def stream_live(
    user: dict = Depends(require_page("clips")),
):
    """Server-sent events: pushes a heartbeat every 15s and a payload
    on every new newsroom_segments row (Postgres LISTEN/NOTIFY).

    Channel: 'newsroom_segment'. The migration 053 trigger emits a
    JSON payload with segment_id + broadcast_id + is_live + created_at.

    Clients consume with `new EventSource('/api/newsroom/stream/live')`
    and listen for `event: segment` and `event: heartbeat`.
    """
    return StreamingResponse(
        _live_event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


async def _live_event_stream() -> AsyncIterator[bytes]:
    dsn = _async_pg_dsn()
    conn: Optional[asyncpg.Connection] = None
    queue: asyncio.Queue = asyncio.Queue(maxsize=1024)

    def _enqueue(connection, pid, channel, payload):
        # Synchronous callback fired by asyncpg in the conn's event loop.
        try:
            queue.put_nowait(payload)
        except asyncio.QueueFull:
            # Drop oldest if a slow client backs us up
            try:
                queue.get_nowait()
                queue.put_nowait(payload)
            except Exception:
                pass

    try:
        conn = await asyncpg.connect(dsn)
        await conn.add_listener("newsroom_segment", _enqueue)
        # Initial comment so reverse proxies flush headers immediately
        yield b": newsroom-sse-connected\n\n"

        while True:
            try:
                payload = await asyncio.wait_for(queue.get(), timeout=15.0)
                yield (
                    b"event: segment\ndata: " + payload.encode("utf-8") + b"\n\n"
                )
            except asyncio.TimeoutError:
                yield b"event: heartbeat\ndata: {}\n\n"
    except asyncio.CancelledError:
        # Client disconnected
        pass
    except Exception as exc:  # noqa: BLE001
        logger.warning("newsroom SSE failed: %s", exc)
    finally:
        if conn is not None:
            try:
                await conn.remove_listener("newsroom_segment", _enqueue)
            except Exception:
                pass
            try:
                await conn.close()
            except Exception:
                pass
