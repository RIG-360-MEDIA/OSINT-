"""
Always-on per-channel digest for THE NEWSROOM WALL.

YouTube live news streams from Telugu broadcasters universally disable
auto-captions on the live broadcast itself. But the same channels
upload short editorial clips of the live stream every 5–30 minutes,
and those VOD uploads DO have YT auto-generated captions in Telugu /
Hindi / Tamil / English.

So this task does, every 60 s:

  1. For each `is_live_24x7=TRUE` active channel, list the last 5 VOD
     uploads via yt-dlp (cheap, flat playlist).

  2. For each upload, fetch auto-captions via youtube_transcript_api
     (cheap HTTP, free, routes through the same SOCKS proxy as yt-dlp
     for IP-reputation hygiene).

  3. Concat the most recent hour of captions into a per-channel buffer.

  4. Ask Cerebras for top 5 phrases / top 3 stories / 1-line summary
     / matched entity ids.

  5. Upsert into `newsroom_channel_live_digest` (one row per channel).

The WALL UI fetches `/api/newsroom/wall` and gets each channel's
digest joined to the channel row for personalised re-ranking against
the user's watched entities.

Trade-off: digest reflects the last ~30 min of editorial focus, not
literal "this very second" — but the WALL also embeds the live video
so users can watch the literal stream while reading the digest.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

import psycopg2
import psycopg2.extras

from backend.celery_app import app
from backend.nlp.groq_client import call_groq, GroqCallFailed, GroqQuotaExhausted

logger = logging.getLogger(__name__)


_UPLOADS_PER_CHANNEL = 5
_DIGEST_MAX_PHRASES = 5
_DIGEST_MAX_STORIES = 3
_PROXY_RETRY = 2


def _pg_url() -> str:
    return os.environ.get(
        "DATABASE_URL_SYNC",
        "postgresql://rig:rigpassword@rig-postgres:5432/rig",
    )


def _list_recent_uploads(handle: str) -> list[dict[str, str]]:
    """Use yt-dlp flat playlist to fetch the last N upload IDs for a handle."""
    import yt_dlp

    url = f"https://www.youtube.com/@{handle.lstrip('@')}/videos"
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": "in_playlist",
        "playlistend": _UPLOADS_PER_CHANNEL,
        "socket_timeout": 15,
        "extractor_retries": 1,
        "retries": 1,
    }
    cookies = os.getenv("YOUTUBE_COOKIES_PATH", "").strip()
    if cookies and os.path.exists(cookies):
        opts["cookiefile"] = cookies
    proxy = os.getenv("YOUTUBE_PROXY_URL", "").strip()
    if proxy:
        opts["proxy"] = proxy

    try:
        with yt_dlp.YoutubeDL(opts) as y:
            info = y.extract_info(url, download=False)
    except Exception as exc:  # noqa: BLE001
        logger.info("uploads list failed for @%s: %s", handle, str(exc)[:120])
        return []

    out: list[dict[str, str]] = []
    for e in (info.get("entries") or [])[:_UPLOADS_PER_CHANNEL]:
        vid = e.get("id") or ""
        title = (e.get("title") or "")[:200]
        if vid:
            out.append({"id": vid, "title": title})
    return out


def _fetch_captions_for_video(vid: str, conn) -> str:
    """Return captions for a VOD, reading from cache first.

    On cache miss, fetches via youtube-transcript-api through the
    SOCKS proxy and persists to `newsroom_vod_caption_cache`. Captions
    on a finished VOD never change, so we fetch each video_id once.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT caption_text FROM newsroom_vod_caption_cache WHERE video_id = %s",
            (vid,),
        )
        row = cur.fetchone()
    if row and row[0]:
        return row[0]

    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        from youtube_transcript_api.proxies import GenericProxyConfig
    except ImportError:
        return ""

    proxy_url = os.getenv("YOUTUBE_PROXY_URL", "").strip()
    if proxy_url:
        api = YouTubeTranscriptApi(
            proxy_config=GenericProxyConfig(http_url=proxy_url, https_url=proxy_url)
        )
    else:
        api = YouTubeTranscriptApi()

    last_exc: BaseException | None = None
    fetched: Any = None
    for _ in range(_PROXY_RETRY):
        try:
            fetched = api.fetch(vid, languages=["te", "te-IN", "hi", "ta", "en"])
            break
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            time.sleep(0.4)
    if fetched is None:
        logger.info("captions fetch failed for %s: %s", vid, str(last_exc)[:120])
        return ""

    parts: list[str] = []
    lang: str | None = None
    for s in fetched:
        text = (getattr(s, "text", None) or "").replace("\n", " ").strip()
        if text:
            parts.append(text)
    text_blob = " ".join(parts)
    try:
        lang = getattr(fetched, "language_code", None)
    except Exception:  # noqa: BLE001
        lang = None

    if text_blob:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO newsroom_vod_caption_cache (video_id, caption_text, language)
                VALUES (%s, %s, %s)
                ON CONFLICT (video_id) DO NOTHING
                """,
                (vid, text_blob[:200000], lang),
            )
    return text_blob


_DIGEST_SYSTEM = """You are a Telugu/Indian news desk editor digesting recent broadcast captions for a single news channel.

You will be given the last ~30-60 minutes of auto-captions transcribed from short clips uploaded by ONE Telugu news channel during their live broadcast.

Return STRICT JSON with these exact keys:
  "summary":      a single English sentence (≤ 18 words) summarising the channel's current editorial focus
  "top_phrases":  array of up to 5 strings — the most distinctive sub-headlines / phrases (English, ≤ 10 words each)
  "top_stories":  array of up to 3 objects {"headline": "...", "blurb": "..."} — distinct news threads
  "entities":     array of up to 8 proper-noun strings — politicians, parties, places, organisations mentioned

Output ONLY a JSON object. No prose, no markdown. If the captions are empty or unintelligible, return {"summary":"","top_phrases":[],"top_stories":[],"entities":[]}.
"""


async def _llm_digest(caption_text: str) -> dict[str, Any]:
    user = f"Captions (concatenated, most recent uploads first):\n\n{caption_text[:9000]}"
    try:
        raw = await call_groq(
            system=_DIGEST_SYSTEM,
            user=user,
            task_type="brief_generation",
            json_response=True,
        )
    except (GroqCallFailed, GroqQuotaExhausted) as exc:
        logger.info("digest llm failed: %s", exc)
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    return parsed


def _resolve_entity_ids(conn, entity_names: list[str]) -> list[str]:
    if not entity_names:
        return []
    cleaned = [n.strip() for n in entity_names if isinstance(n, str) and n.strip()]
    if not cleaned:
        return []
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT id::text
              FROM entity_dictionary
             WHERE LOWER(canonical_name) = ANY(%s)
                OR aliases && %s::text[]
            """,
            ([n.lower() for n in cleaned], cleaned),
        )
        return [r[0] for r in (cur.fetchall() or [])]


@app.task(
    name="tasks.newsroom.live_captions_poll",
    queue="nlp",
    max_retries=0,
    soft_time_limit=540,
)
def live_captions_poll() -> dict:
    """Refresh per-channel digest from recent VOD upload captions."""
    conn = psycopg2.connect(_pg_url())
    conn.autocommit = True
    stats = {"checked": 0, "captioned": 0, "digested": 0, "errors": 0}

    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id::text AS channel_id, name, language, yt_handle,
                       current_live_video_id AS video_id
                  FROM newsroom_channels
                 WHERE active = TRUE AND is_live_24x7 = TRUE
                """
            )
            channels = cur.fetchall() or []

        loop = asyncio.new_event_loop()
        try:
            for ch in channels:
                stats["checked"] += 1
                uploads = _list_recent_uploads(ch["yt_handle"])
                if not uploads:
                    stats["errors"] += 1
                    continue

                texts: list[str] = []
                upload_ids: list[str] = []
                for u in uploads:
                    cap = _fetch_captions_for_video(u["id"], conn)
                    if cap:
                        texts.append(f"[{u['title']}]\n{cap}")
                        upload_ids.append(u["id"])
                    time.sleep(0.6)
                if not texts:
                    continue
                stats["captioned"] += 1

                merged = "\n\n".join(texts)[:12000]
                digest = loop.run_until_complete(_llm_digest(merged))
                summary = (digest.get("summary") or "").strip()
                phrases = digest.get("top_phrases") or []
                stories = digest.get("top_stories") or []
                entities = digest.get("entities") or []
                if not isinstance(phrases, list):
                    phrases = []
                if not isinstance(stories, list):
                    stories = []
                phrases = [str(p)[:120] for p in phrases][:_DIGEST_MAX_PHRASES]
                stories = [s for s in stories if isinstance(s, dict)][:_DIGEST_MAX_STORIES]
                entity_ids = _resolve_entity_ids(conn, entities) if entities else []

                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO newsroom_channel_live_digest
                          (channel_id, video_id, caption_buffer, last_caption_at,
                           top_phrases, top_stories, summary, entity_ids, generated_at)
                        VALUES (%s, %s, %s, now(), %s::jsonb, %s::jsonb, %s, %s::uuid[], now())
                        ON CONFLICT (channel_id) DO UPDATE
                          SET video_id        = EXCLUDED.video_id,
                              caption_buffer  = EXCLUDED.caption_buffer,
                              last_caption_at = EXCLUDED.last_caption_at,
                              top_phrases     = EXCLUDED.top_phrases,
                              top_stories     = EXCLUDED.top_stories,
                              summary         = EXCLUDED.summary,
                              entity_ids      = EXCLUDED.entity_ids,
                              generated_at    = now()
                        """,
                        (
                            ch["channel_id"],
                            ch["video_id"] or (upload_ids[0] if upload_ids else ""),
                            merged[-4000:],
                            json.dumps(phrases),
                            json.dumps(stories),
                            summary,
                            entity_ids,
                        ),
                    )
                stats["digested"] += 1
        finally:
            loop.close()
    finally:
        conn.close()

    logger.info("live_captions_poll: %s", stats)
    return stats
