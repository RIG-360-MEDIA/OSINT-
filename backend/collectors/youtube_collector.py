"""
YouTube channel monitor and transcript processor.

Flow per channel:
  1. List recent videos via YouTube Data API v3
  2. For each new video: fetch timestamped transcript (cookies bypass IP blocks)
  3. Send transcript to Groq for entity relevance analysis
  4. Groq identifies important segments with English summaries
  5. Store medium/high importance clips with LaBSE embeddings
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import random
from datetime import datetime, timedelta, timezone

import httpx

logger = logging.getLogger(__name__)

_CLIP_LEAD_IN     = 5    # seconds before mention to give context
_CLIP_MIN_WINDOW  = 15   # never shorter than this
_CLIP_MAX_WINDOW  = 120  # never longer than this

# Stage 4A — chunked analysis instead of lossy sampling.
# Groq sees a 10-minute window of transcript at a time; long videos go in
# multiple windows so we never skip a mention.
_CHUNK_SECONDS         = 600   # 10 min per Groq call
_MAX_CHUNK_CHARS       = 6000  # per chunk
_MAX_CHUNKS_PER_VIDEO  = 6     # cap total Groq calls per video (1hr)

# Stage 3 — Whisper fallback caps (cheap, free on our 16-key Groq pool).
_WHISPER_MAX_DURATION_S = 30 * 60   # only transcribe up to 30 min
_WHISPER_TIER_FLOOR     = "tier_2"  # don't whisper-transcribe tier_3 channels

# Circuit breaker: once we see N consecutive IP blocks, skip transcript path entirely
_IP_BLOCK_THRESHOLD = 3
_ip_block_streak = 0

# API keys marked as quota-exhausted for this process run
_exhausted_api_keys: set[str] = set()


def _is_quota_error(resp_text: str) -> bool:
    return "quotaExceeded" in resp_text or "quota" in resp_text.lower()


# ── Stage 4B — region-agnostic disambiguation ────────────────────────────────

async def load_alias_rules(db, region: str = "telangana") -> str:
    """Load entity_aliases rows for a region and format as a Groq prompt block.

    Returns an empty string if the table is empty so the prompt stays valid.
    """
    from sqlalchemy import text

    try:
        result = await db.execute(
            text("""
                SELECT canonical_name, alias, COALESCE(notes, '') AS notes
                FROM entity_aliases
                WHERE region = :region OR region IS NULL
                ORDER BY canonical_name, alias
            """),
            {"region": region},
        )
        rows = result.fetchall()
    except Exception:
        logger.warning("alias rules load failed — using empty block", exc_info=True)
        return ""

    if not rows:
        return ""

    grouped: dict[str, list[tuple[str, str]]] = {}
    for r in rows:
        grouped.setdefault(r.canonical_name, []).append((r.alias, r.notes))

    lines = ["CRITICAL ENTITY DISAMBIGUATION (use the EXACT canonical name):"]
    for canonical, items in grouped.items():
        aliases = " / ".join(f"'{a}'" for a, _ in items)
        notes = next((n for _, n in items if n), "")
        suffix = f" — {notes}" if notes else ""
        lines.append(f"- {aliases} = {canonical}{suffix}")
    return "\n".join(lines)


def get_api_keys() -> list[str]:
    """Return non-empty API keys from YOUTUBE_API_KEY + YOUTUBE_API_KEY_2..N env vars."""
    keys: list[str] = []
    primary = os.getenv("YOUTUBE_API_KEY", "").strip()
    if primary:
        keys.append(primary)
    for i in range(2, 6):
        k = os.getenv(f"YOUTUBE_API_KEY_{i}", "").strip()
        if k and k not in keys:
            keys.append(k)
    return keys


# ── Channel video listing ─────────────────────────────────────────────────────

async def _fetch_channel_videos_rss(
    channel_id: str,
    since_dt: datetime | None = None,
    max_results: int = 10,
) -> list[dict] | None:
    """
    Fetch recent videos from a channel via YouTube's public Atom feed.

    YouTube publishes a free, unauthenticated RSS feed for every channel at
    ``https://www.youtube.com/feeds/videos.xml?channel_id=<id>``. The feed
    carries the latest 15 videos with title, video_id, published_at, channel
    name, and description — exactly the fields we need for downstream NLP
    and transcript fetching.

    Returns a list of dicts in the same shape as :func:`fetch_channel_videos`,
    or ``None`` if the fetch / parse failed (caller should fall back to the
    Data-API path on ``None``; an empty list means "RSS worked, channel just
    has no new videos since since_dt").

    No API key, no quota, no auth. Adopted to escape the YouTube Data API
    /search quota wall (100 units per channel per cycle, 86k/day at our
    fan-out — see DEPLOYMENT_NOTES.md).
    """
    import xml.etree.ElementTree as ET

    NS = {
        "atom": "http://www.w3.org/2005/Atom",
        "yt": "http://www.youtube.com/xml/schemas/2015",
        "media": "http://search.yahoo.com/mrss/",
    }
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url)
        if resp.status_code != 200:
            logger.info(
                "RSS feed for channel %s returned HTTP %s — will fall back to API",
                channel_id, resp.status_code,
            )
            return None
        root = ET.fromstring(resp.text)
    except Exception:
        logger.info(
            "RSS feed fetch failed for channel %s — will fall back to API",
            channel_id, exc_info=True,
        )
        return None

    channel_name = (root.findtext("atom:title", default="", namespaces=NS) or "").strip()

    videos: list[dict] = []
    for entry in root.findall("atom:entry", NS):
        video_id = (entry.findtext("yt:videoId", default="", namespaces=NS) or "").strip()
        if not video_id:
            continue
        title = (entry.findtext("atom:title", default="", namespaces=NS) or "").strip()
        published_str = (entry.findtext("atom:published", default="", namespaces=NS) or "").strip()

        description = ""
        media_group = entry.find("media:group", NS)
        if media_group is not None:
            description = (
                media_group.findtext("media:description", default="", namespaces=NS) or ""
            ).strip()

        # Filter to the high-water mark.
        if since_dt is not None and published_str:
            try:
                pub_dt = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
                if pub_dt < since_dt:
                    continue
            except Exception:
                # Don't drop on parse error — let the downstream pipeline decide.
                pass

        videos.append({
            "video_id":     video_id,
            "title":        title,
            "published_at": published_str,
            "channel_name": channel_name,
            "description":  description,
        })
        if len(videos) >= max_results:
            break

    return videos


async def _fetch_channel_videos_ytdlp(
    channel_id: str,
    since_dt: datetime | None = None,
    max_results: int = 10,
) -> list[dict] | None:
    """
    Fetch channel videos via yt-dlp. Used when RSS is blocked (YouTube
    blocks data-center IPs from RSS feeds) and to escape the Data API
    /search 100-unit quota.

    Reads cookies from YOUTUBE_COOKIES_PATH if set — an authenticated
    session bypasses the IP blocks YouTube applies to anonymous data-
    center traffic. Falls through to the Data API (caller-side) if this
    path returns None.

    Returns the same shape as :func:`fetch_channel_videos`, or ``None``
    on failure.
    """
    import yt_dlp  # type: ignore

    cookies_path = _get_cookies_path()
    proxy_url = _get_proxy_url()

    ydl_opts: dict = {
        "extract_flat": "in_playlist",
        "skip_download": True,
        "playlistend": max(1, max_results),
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
        # Skip yt-dlp's own auth-check probe. Without this, yt-dlp aborts
        # the channel fetch when it can't confirm a logged-in session has
        # access — even when the channel is fully public. The cookies we
        # ship are for IP-block bypass only; we are not trying to access
        # private content.
        "extractor_args": {"youtubetab": {"skip": ["authcheck"]}},
    }
    if cookies_path:
        ydl_opts["cookiefile"] = cookies_path
    if proxy_url:
        ydl_opts["proxy"] = proxy_url

    url = f"https://www.youtube.com/channel/{channel_id}/videos"

    def _extract():
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if info is None:
                    return None
                return info.get("entries") or []
        except Exception:
            logger.info(
                "yt-dlp channel listing failed for %s — will fall back to API",
                channel_id, exc_info=True,
            )
            return None

    loop = asyncio.get_event_loop()
    entries = await loop.run_in_executor(None, _extract)
    if entries is None:
        return None

    videos: list[dict] = []
    for entry in entries:
        if not entry or not entry.get("id"):
            continue
        video_id = entry["id"]
        title = (entry.get("title") or "").strip()

        # Best-effort published_at: yt-dlp may give either a unix timestamp
        # or upload_date (YYYYMMDD); both are optional in flat extraction.
        published_at = ""
        ts = entry.get("timestamp")
        if ts:
            try:
                published_at = datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                )
            except Exception:
                pass
        if not published_at and entry.get("upload_date"):
            try:
                ud = entry["upload_date"]
                published_at = f"{ud[0:4]}-{ud[4:6]}-{ud[6:8]}T00:00:00Z"
            except Exception:
                pass

        # High-water-mark filter (skip if older than since_dt).
        if since_dt is not None and published_at:
            try:
                pub_dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
                if pub_dt < since_dt:
                    continue
            except Exception:
                pass

        videos.append({
            "video_id":     video_id,
            "title":        title,
            "published_at": published_at,
            "channel_name": (entry.get("channel") or "").strip(),
            "description":  (entry.get("description") or "").strip(),
        })
        if len(videos) >= max_results:
            break

    return videos


async def fetch_channel_videos(
    channel_id: str,
    api_key: str | list[str],
    since_days: int = 2,
    since_dt: datetime | None = None,
    max_results: int = 10,
    exclude_shorts: bool = True,
) -> list[dict]:
    """
    Fetch recent videos from a channel via YouTube Data API v3.

    Stage 2 upgrades:
      - `since_dt` (high-water mark) takes precedence over `since_days` so we
        only ask the API for videos newer than what we last saw on this channel.
      - `max_results` is now caller-controlled (tier-aware in the task layer).
      - `exclude_shorts` filters out videos < 60s (`videoDuration=medium|long`).

    Accepts either a single key or a list of keys. On HTTP 403 with quotaExceeded
    the current key is marked exhausted for the rest of the process and the next
    key is tried automatically.
    """
    if since_dt is not None:
        since = since_dt
    else:
        since = datetime.now(timezone.utc) - timedelta(days=since_days)

    # Try the free YouTube RSS feed first. Falls back to the Data API only
    # if RSS itself failed (HTTP / parse error). An empty RSS result is
    # treated as success ("channel has no new videos since since"); in that
    # case we do NOT fall back to the API because the API would return the
    # same empty set at 100 units / channel.
    rss_videos = await _fetch_channel_videos_rss(
        channel_id=channel_id,
        since_dt=since,
        max_results=max_results,
    )
    if rss_videos is not None:
        logger.info(
            "youtube/rss channel=%s returned %d videos",
            channel_id, len(rss_videos),
        )
        return rss_videos

    # Path 2: yt-dlp + cookies. Works when RSS is blocked (data-center IPs)
    # and bypasses the /search quota wall.
    ytdlp_videos = await _fetch_channel_videos_ytdlp(
        channel_id=channel_id,
        since_dt=since,
        max_results=max_results,
    )
    if ytdlp_videos is not None:
        logger.info(
            "youtube/yt-dlp channel=%s returned %d videos",
            channel_id, len(ytdlp_videos),
        )
        return ytdlp_videos

    published_after = since.strftime("%Y-%m-%dT%H:%M:%SZ")

    keys = [api_key] if isinstance(api_key, str) else list(api_key)
    available = [k for k in keys if k and k not in _exhausted_api_keys]
    if not available:
        logger.warning("All YouTube API keys exhausted — skipping channel %s", channel_id)
        return []

    async def _get(client: httpx.AsyncClient, url: str, params: dict) -> httpx.Response | None:
        nonlocal available
        for key in list(available):
            r = await client.get(url, params={**params, "key": key}, timeout=15)
            if r.status_code == 403 and _is_quota_error(r.text):
                logger.warning("API key ...%s quota exceeded — rotating", key[-6:])
                _exhausted_api_keys.add(key)
                available = [k for k in available if k != key]
                continue
            return r
        return None

    try:
        async with httpx.AsyncClient() as client:
            params = {
                "part":           "snippet",
                "channelId":      channel_id,
                "type":           "video",
                "order":          "date",
                "publishedAfter": published_after,
                "maxResults":     max(1, min(max_results, 50)),
            }
            if exclude_shorts:
                # YouTube API: medium = 4-20min, long = >20min. Shorts (<4min) excluded.
                # We only drop the <60s definition; "short videos" between 4-20min stay.
                params["videoDuration"] = "medium"
            r = await _get(
                client,
                "https://www.googleapis.com/youtube/v3/search",
                params,
            )
            if r is None or r.status_code != 200:
                if r is not None:
                    logger.warning(
                        "YouTube API %s for channel %s: %s",
                        r.status_code, channel_id, r.text[:200],
                    )
                return []

            items = r.json().get("items", [])
            videos = [
                {
                    "video_id":     item["id"]["videoId"],
                    "title":        item["snippet"]["title"],
                    "published_at": item["snippet"]["publishedAt"],
                    "channel_name": item["snippet"]["channelTitle"],
                    "description":  item["snippet"].get("description", ""),
                }
                for item in items
                if item.get("id", {}).get("videoId")
            ]

            if not videos:
                return []

            ids = ",".join(v["video_id"] for v in videos)
            rv = await _get(
                client,
                "https://www.googleapis.com/youtube/v3/videos",
                {"part": "snippet", "id": ids},
            )
            if rv is not None and rv.status_code == 200:
                desc_map = {
                    item["id"]: item["snippet"].get("description", "")
                    for item in rv.json().get("items", [])
                }
                videos = [
                    {**v, "description": desc_map.get(v["video_id"], v["description"])}
                    for v in videos
                ]

            return videos

    except Exception:
        logger.exception("Channel video fetch failed for %s", channel_id)
        return []


# ── Transcript fetching ───────────────────────────────────────────────────────

def _get_cookies_path() -> str | None:
    """Return path to YouTube cookies file if configured."""
    path = os.getenv("YOUTUBE_COOKIES_PATH", "")
    if path and os.path.exists(path):
        return path
    return None


def _get_proxy_url() -> str | None:
    """Return SOCKS/HTTP proxy URL for bypassing YouTube IP blocks."""
    return os.getenv("YOUTUBE_PROXY_URL") or None


async def fetch_transcript(video_id: str) -> list[dict] | None:
    """
    Fetch timestamped transcript for a public YouTube video.

    Returns list of {text, start, duration, language}.
    Passes cookies if YOUTUBE_COOKIES_PATH is set (bypasses IP blocks).
    Adds polite random delay to avoid rate limiting.
    """
    global _ip_block_streak

    # If we've seen too many IP blocks in a row, short-circuit to avoid wasting time
    if _ip_block_streak >= _IP_BLOCK_THRESHOLD:
        return None

    from youtube_transcript_api import YouTubeTranscriptApi
    from youtube_transcript_api._errors import (
        NoTranscriptFound,
        TranscriptsDisabled,
        VideoUnplayable,
    )

    # Collect all known IP-block exception types across library versions
    _block_errors: list[type] = []
    for name in ("RequestBlocked", "IpBlocked", "RequestBlockedByYouTube"):
        try:
            import youtube_transcript_api._errors as _e
            cls = getattr(_e, name, None)
            if cls:
                _block_errors.append(cls)
        except Exception:
            pass
    _BLOCK_ERRORS = tuple(_block_errors) if _block_errors else (Exception,)

    # Polite random delay between fetches
    await asyncio.sleep(random.uniform(1.5, 3.5))

    cookies_path = _get_cookies_path()
    proxy_url = _get_proxy_url()

    proxy_config = None
    if proxy_url:
        from youtube_transcript_api.proxies import GenericProxyConfig
        proxy_config = GenericProxyConfig(http_url=proxy_url, https_url=proxy_url)

    api_kwargs: dict = {}
    if cookies_path:
        api_kwargs["cookies"] = cookies_path
    if proxy_config is not None:
        api_kwargs["proxy_config"] = proxy_config
    try:
        api = YouTubeTranscriptApi(**api_kwargs)
    except TypeError:
        # Older youtube_transcript_api versions reject the 'cookies' kwarg.
        # Fall back to constructing without it; transcripts may be slightly
        # less reliable but the rest of the pipeline (yt-dlp video listing,
        # storage, NLP) keeps working.
        api_kwargs.pop("cookies", None)
        api = YouTubeTranscriptApi(**api_kwargs)

    try:
        lang = "en"
        data = None
        for try_lang in ["en", "te", "hi", "kn", "ta"]:
            try:
                data = api.fetch(video_id, languages=[try_lang])
                lang = try_lang
                break
            except Exception:
                continue

        if data is None:
            transcript_list = api.list(video_id)
            for t in transcript_list:
                data = api.fetch(video_id, languages=[t.language_code])
                lang = t.language_code
                break

        if data is None:
            raise NoTranscriptFound(video_id, [], {})  # type: ignore[arg-type]

        _ip_block_streak = 0  # reset on successful fetch
        return [
            {
                "text":     item.text,
                "start":    item.start,
                "duration": item.duration,
                "language": lang,
            }
            for item in data
        ]

    except VideoUnplayable:
        logger.info("Video %s is unplayable (live/private) — skipping", video_id)
        return None
    except _BLOCK_ERRORS:
        _ip_block_streak += 1
        logger.warning(
            "IP blocked fetching transcript for %s (streak=%d) — skipping to metadata",
            video_id, _ip_block_streak,
        )
        return None
    except (TranscriptsDisabled, NoTranscriptFound):
        logger.info("No transcript available for %s", video_id)
        return None
    except Exception:
        logger.warning("Transcript fetch failed for %s", video_id, exc_info=True)
        return None


async def _fetch_transcript_ytdlp(video_id: str) -> list[dict] | None:
    """Fallback: extract subtitle URLs via yt-dlp and download the VTT directly."""
    try:
        import tempfile

        import httpx
        import yt_dlp

        url = f"https://youtube.com/watch?v={video_id}"
        cookies_path = _get_cookies_path()
        proxy_url = _get_proxy_url()

        ydl_opts: dict = {
            "skip_download":       True,
            "quiet":               True,
            "no_warnings":         True,
            "format":              "bestaudio/worst",
            "ignore_no_formats_error": True,
            "check_formats":       False,
        }
        if cookies_path:
            ydl_opts["cookiefile"] = cookies_path
        if proxy_url:
            ydl_opts["proxy"] = proxy_url

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = await asyncio.to_thread(ydl.extract_info, url, download=False)

        # Prefer manual subs, fall back to auto-captions; prefer en, then te/hi
        sub_sources = [
            ("subtitles",          info.get("subtitles") or {}),
            ("automatic_captions", info.get("automatic_captions") or {}),
        ]

        for _src_name, src in sub_sources:
            for try_lang in ["en", "en-US", "en-GB", "te", "hi"]:
                tracks = src.get(try_lang)
                if not tracks:
                    continue
                # Prefer a VTT track; otherwise force vtt format via URL param
                track = next(
                    (t for t in tracks if t.get("ext") == "vtt"), tracks[0]
                )
                raw_url = track.get("url")
                if not raw_url:
                    continue
                vtt_url = raw_url
                if track.get("ext") != "vtt":
                    sep = "&" if "?" in vtt_url else "?"
                    # Replace fmt param if present, else append
                    if "fmt=" in vtt_url:
                        import re
                        vtt_url = re.sub(r"fmt=[^&]+", "fmt=vtt", vtt_url)
                    else:
                        vtt_url = f"{vtt_url}{sep}fmt=vtt"

                cookie_jar = None
                if cookies_path:
                    from http.cookiejar import MozillaCookieJar
                    try:
                        jar = MozillaCookieJar(cookies_path)
                        jar.load(ignore_discard=True, ignore_expires=True)
                        cookie_jar = jar
                    except Exception:
                        cookie_jar = None

                client_kwargs: dict = {
                    "timeout": 15,
                    "cookies": cookie_jar,
                    "headers": {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"},
                }
                if proxy_url:
                    client_kwargs["proxy"] = proxy_url
                async with httpx.AsyncClient(**client_kwargs) as client:
                    r = await client.get(vtt_url)
                    if r.status_code != 200:
                        continue
                    with tempfile.NamedTemporaryFile(
                        "w", suffix=".vtt", delete=False, encoding="utf-8",
                    ) as tmp:
                        tmp.write(r.text)
                        tmp_path = tmp.name
                try:
                    segs = _parse_vtt(tmp_path, try_lang[:2])
                    if segs:
                        return segs
                finally:
                    try:
                        os.unlink(tmp_path)
                    except OSError:
                        pass

        return None
    except Exception:
        logger.debug("yt-dlp transcript failed for %s", video_id, exc_info=True)
        return None


def _parse_vtt(vtt_path: str, language: str) -> list[dict]:
    """Parse WebVTT subtitle file into transcript segments."""
    try:
        import webvtt

        segments = []
        for caption in webvtt.read(vtt_path):
            start = _vtt_time_to_seconds(caption.start)
            end   = _vtt_time_to_seconds(caption.end)
            segments.append({
                "text":     caption.text.strip(),
                "start":    start,
                "duration": end - start,
                "language": language,
            })
        return segments
    except Exception:
        return []


def _vtt_time_to_seconds(time_str: str) -> float:
    """Convert HH:MM:SS.mmm to seconds."""
    parts = time_str.split(":")
    if len(parts) == 3:
        h, m, s = parts
        return int(h) * 3600 + int(m) * 60 + float(s)
    elif len(parts) == 2:
        m, s = parts
        return int(m) * 60 + float(s)
    return float(parts[0])


# ── Groq transcript analysis ──────────────────────────────────────────────────

def _chunk_transcript(transcript: list[dict]) -> list[list[dict]]:
    """Split transcript into _CHUNK_SECONDS-second windows so long videos lose
    no granularity. Each chunk is analysed by Groq independently."""
    if not transcript:
        return []
    chunks: list[list[dict]] = []
    current: list[dict] = []
    chunk_start = transcript[0].get("start", 0)
    for seg in transcript:
        if seg.get("start", 0) - chunk_start >= _CHUNK_SECONDS and current:
            chunks.append(current)
            current = []
            chunk_start = seg.get("start", 0)
        current.append(seg)
    if current:
        chunks.append(current)
    return chunks[:_MAX_CHUNKS_PER_VIDEO]


async def _analyse_chunk(
    chunk: list[dict],
    video_title: str,
    channel_name: str,
    user_entities: list[str],
    alias_block: str,
) -> list[dict]:
    """Analyse a single transcript chunk with Groq."""
    from backend.nlp.groq_client import FAST_MODEL, call_groq

    if not chunk:
        return []

    lang  = chunk[0].get("language", "en")
    lines = [f"[{int(seg['start'])}s] {seg['text'].strip()}" for seg in chunk]
    transcript_text = "\n".join(lines)[:_MAX_CHUNK_CHARS]
    entities_str    = ", ".join(user_entities)

    system_parts = [
        "You are a political intelligence analyst.",
        f"Analyze this YouTube transcript chunk from channel '{channel_name}'.",
        f"Identify any mentions of these monitored entities: {entities_str}.",
        "For each mention, assess whether it contains actionable intelligence "
        "(policy announcements, controversies, statements, events).",
    ]
    if alias_block:
        system_parts.append(alias_block)
    system_parts.append(
        "Use the EXACT canonical name from the entity list — pick ONLY the person "
        "actually mentioned. Respond ONLY with valid JSON — no markdown. "
        'Schema: {"clips": [{"entity": "exact entity name from list", '
        '"start_seconds": 120, "end_seconds": 150, '
        '"summary": "1-2 sentence English summary of what was said", '
        '"importance": "high|medium|low"}]} '
        'Omit low importance clips. If nothing relevant, return {"clips": []}.'
    )
    system = "\n\n".join(system_parts)

    user_msg = (
        f"Video title: {video_title}\n"
        f"Transcript language: {lang}\n\n"
        f"Transcript (format: [seconds] text):\n{transcript_text}"
    )

    try:
        raw = await call_groq(
            system=system, user=user_msg,
            task_type="transcript_analysis",
            model=FAST_MODEL, json_response=True,
        )
        data  = json.loads(raw) if isinstance(raw, str) else raw
        clips = data.get("clips", [])
    except Exception:
        logger.warning("Groq chunk analysis failed for '%s'", video_title, exc_info=True)
        return []

    entity_lookup = {e.lower(): e for e in user_entities}
    out: list[dict] = []
    for c in clips:
        if not all(k in c for k in ("entity", "start_seconds", "summary")):
            continue
        if c.get("importance", "medium") == "low":
            continue
        canonical = entity_lookup.get(str(c["entity"]).lower())
        if not canonical:
            logger.debug("Rejecting hallucinated entity '%s'", c["entity"])
            continue
        start = int(c.get("start_seconds", 0))
        end   = int(c.get("end_seconds", start + 30))
        out.append({
            "entity":        canonical,
            "start_seconds": start,
            "end_seconds":   end,
            "summary":       c["summary"],
            "importance":    c.get("importance", "medium"),
        })
    return out


async def analyze_transcript_with_groq(
    transcript: list[dict],
    video_title: str,
    channel_name: str,
    user_entities: list[str],
    alias_block: str = "",
) -> list[dict]:
    """
    Stage 4A — chunked, no sampling. The transcript is split into
    _CHUNK_SECONDS windows and each is sent to Groq independently. Mentions
    that fall in any chunk are caught.

    Stage 4B — `alias_block` is the disambiguation prompt loaded from
    `entity_aliases` (region-aware), passed in by the caller. No more
    hardcoded Telangana names.

    Returns aggregated clips across all chunks.
    """
    if not transcript or not user_entities:
        return []

    chunks = _chunk_transcript(transcript)
    if not chunks:
        return []

    coros = [
        _analyse_chunk(chunk, video_title, channel_name, user_entities, alias_block)
        for chunk in chunks
    ]
    results = await asyncio.gather(*coros, return_exceptions=True)

    out: list[dict] = []
    for r in results:
        if isinstance(r, list):
            out.extend(r)
    # Deduplicate clips that fall within 5 s of an existing one for the same entity.
    out.sort(key=lambda c: (c["entity"], c["start_seconds"]))
    deduped: list[dict] = []
    for c in out:
        if deduped and deduped[-1]["entity"] == c["entity"] \
           and abs(c["start_seconds"] - deduped[-1]["start_seconds"]) <= 5:
            continue
        deduped.append(c)
    return deduped


async def analyze_video_metadata_with_groq(
    video_title: str,
    description: str,
    channel_name: str,
    user_entities: list[str],
    alias_block: str = "",
) -> list[dict]:
    """
    Fallback when transcript is unavailable (IP block, no captions).

    Uses video title + description to identify entity relevance via Groq.
    Returns same structure as analyze_transcript_with_groq but start_seconds=0
    (full video embed, no precise timestamp).
    """
    from backend.nlp.groq_client import FAST_MODEL, call_groq

    if not user_entities:
        return []

    content = f"Title: {video_title}\nDescription: {description[:2000]}"
    entities_str = ", ".join(user_entities)

    system_parts = [
        "You are a political intelligence analyst.",
        f"Check if this YouTube video from '{channel_name}' is about any of these entities: {entities_str}.",
        "Flag videos where the entity appears in the title OR is a substantive topic in the description. "
        "Titles in Telugu/Hindi count too — translate mentally.",
    ]
    if alias_block:
        system_parts.append(alias_block)
    system_parts.append(
        "Pick the EXACT canonical name of the person the title/description is actually about. "
        "Respond ONLY with valid JSON. "
        'Schema: {"clips": [{"entity": "exact entity name from my list", "start_seconds": 0, "end_seconds": 30, '
        '"summary": "1-2 sentence English summary of what the video covers about this entity", '
        '"importance": "high|medium|low"}]} '
        'If no relevant entity, return {"clips": []}.'
    )
    system = "\n\n".join(system_parts)

    try:
        raw = await call_groq(
            system=system,
            user=content,
            task_type="transcript_analysis",
            model=FAST_MODEL,
            json_response=True,
        )
        data = json.loads(raw) if isinstance(raw, str) else raw
        entity_lookup = {e.lower(): e for e in user_entities}

        result = []
        for c in data.get("clips", []):
            if not all(k in c for k in ("entity", "summary")):
                continue
            if c.get("importance", "medium") == "low":
                continue
            canonical = entity_lookup.get(str(c["entity"]).lower())
            if not canonical:
                logger.debug("Rejecting hallucinated entity '%s'", c["entity"])
                continue
            result.append({
                "entity":        canonical,
                "start_seconds": 0,
                "end_seconds":   30,
                "summary":       c["summary"],
                "importance":    c.get("importance", "medium"),
                "metadata_only": True,
            })
        return result
    except Exception:
        logger.warning("Groq metadata analysis failed for '%s'", video_title, exc_info=True)
        return []


# ── Stage 3 — Whisper fallback (free on our 16-key Groq pool) ────────────────

async def _fetch_transcript_via_whisper(video_id: str) -> list[dict] | None:
    """
    Last-resort transcript path: download the audio with yt-dlp and transcribe
    via Groq Whisper. Cheap on our Groq key pool, IP-block-immune (audio is
    streamed via the same proxy as yt-dlp).

    Returns segmented transcript ({text, start, duration, language}) or None.
    """
    try:
        import tempfile

        import yt_dlp

        url = f"https://www.youtube.com/watch?v={video_id}"
        cookies_path = _get_cookies_path()
        proxy_url    = _get_proxy_url()

        with tempfile.TemporaryDirectory() as tmpdir:
            # NOTE: yt-dlp format selector. YouTube increasingly DASH-muxes
            # audio so a strict m4a-only selector matches nothing on many
            # videos. Fall through: prefer m4a → any audio-only stream → any
            # stream that has audio. Last fallback ensures we never end up
            # with "Requested format is not available" silently killing the
            # Whisper pipeline (P1-NEW-A in clips audit 2026-04-28).
            audio_path = os.path.join(tmpdir, f"{video_id}.m4a")
            ydl_opts: dict = {
                "format":      "bestaudio[ext=m4a]/bestaudio/best[acodec!=none]/best",
                "outtmpl":     audio_path,
                "quiet":       True,
                "no_warnings": True,
                # don't waste bandwidth on huge debates
                "match_filter": yt_dlp.utils.match_filter_func(f"duration <= {_WHISPER_MAX_DURATION_S}"),
            }
            if cookies_path:
                ydl_opts["cookiefile"] = cookies_path
            if proxy_url:
                ydl_opts["proxy"] = proxy_url

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    await asyncio.to_thread(ydl.download, [url])
            except Exception as exc:
                # Promoted DEBUG → WARNING so silent failures stop hiding.
                logger.warning(
                    "Whisper: yt-dlp audio download failed for %s: %s",
                    video_id, exc,
                )
                return None

            if not os.path.exists(audio_path):
                logger.warning(
                    "Whisper: yt-dlp produced no audio file for %s", video_id
                )
                return None
            audio_size = os.path.getsize(audio_path)
            if audio_size < 1024:
                logger.warning(
                    "Whisper: audio file for %s too small (%d bytes)",
                    video_id, audio_size,
                )
                return None

            from backend.nlp.groq_client import transcribe_audio_with_whisper

            try:
                segments = await transcribe_audio_with_whisper(audio_path)
            except Exception:
                logger.warning("Whisper transcription failed for %s", video_id, exc_info=True)
                return None

            if not segments:
                logger.warning(
                    "Whisper returned 0 segments for %s", video_id
                )
                return None
            logger.info("Whisper transcribed %s (%d segments)", video_id, len(segments))
            return segments
    except Exception:
        # Promoted DEBUG → WARNING — outer catch must surface to operators.
        logger.warning("Whisper fallback errored for %s", video_id, exc_info=True)
        return None


def get_transcript_text_at(
    transcript: list[dict],
    start_sec: int,
    window: int = 30,
) -> str:
    """Extract original transcript text around a given timestamp."""
    relevant = [
        seg["text"]
        for seg in transcript
        if start_sec - 5 <= seg.get("start", 0) <= start_sec + window
    ]
    return " ".join(relevant)[:500] if relevant else ""


# ── Single-video processing ───────────────────────────────────────────────────

async def process_video(
    video: dict,
    channel_id: str,
    user_entities: list[str],
    entity_dictionary: dict,
    db,
) -> int:
    """
    Fetch transcript for a video, analyze with Groq, store relevant clips.

    Returns number of clip records created.
    """
    from sqlalchemy import text

    from backend.nlp.nlp_embedding import generate_embedding

    video_id = video["video_id"]

    existing = await db.execute(
        text("SELECT COUNT(*) AS cnt FROM youtube_clips WHERE video_id = :vid"),
        {"vid": video_id},
    )
    if existing.fetchone().cnt > 0:
        logger.debug("Video %s already processed — skipping", video_id)
        return 0

    # Stage 4B — load region-aware disambiguation rules from DB.
    alias_block = await load_alias_rules(db, region="telangana")

    transcript = await fetch_transcript(video_id)
    transcript_source = "captions" if transcript else None

    # If youtube-transcript-api failed (IP block / no captions), try yt-dlp fallback
    if not transcript:
        transcript = await _fetch_transcript_ytdlp(video_id)
        if transcript:
            transcript_source = "yt_dlp"
            logger.info("yt-dlp transcript fetched for %s (%d segs)", video_id, len(transcript))

    # Stage 3 — Whisper fallback before giving up to metadata-only.
    if not transcript:
        transcript = await _fetch_transcript_via_whisper(video_id)
        if transcript:
            transcript_source = "whisper"

    if transcript:
        clips_from_groq = await analyze_transcript_with_groq(
            transcript=transcript,
            video_title=video["title"],
            channel_name=video["channel_name"],
            user_entities=user_entities,
            alias_block=alias_block,
        )
        lang = transcript[0].get("language", "en")
    else:
        # Transcript unavailable (IP block, no captions) — fall back to title+description
        transcript_source = "metadata"
        logger.info("No transcript for %s — using metadata analysis", video_id)
        clips_from_groq = await analyze_video_metadata_with_groq(
            video_title=video["title"],
            description=video.get("description", ""),
            channel_name=video["channel_name"],
            user_entities=user_entities,
            alias_block=alias_block,
        )
        lang = "en"

    if not clips_from_groq:
        logger.info("No relevant clips found in %s", video_id)
        return 0
    clips_created = 0

    for clip_info in clips_from_groq:
        mention_time     = clip_info["start_seconds"]
        groq_end         = clip_info.get("end_seconds", mention_time + 30)
        metadata_only    = clip_info.get("metadata_only", False)

        if metadata_only:
            # No real timestamp — keep DB columns and embed_url consistent
            # by zeroing both. Frontend can detect (start == end == 0) and
            # treat as "play full video" (P1-2 in clips audit 2026-04-28).
            clip_start = 0
            clip_end   = 0
            embed_url = (
                f"https://www.youtube.com/embed/{video_id}"
                f"?autoplay=0&rel=0&modestbranding=1"
            )
        else:
            # Use Groq's end_seconds (it knows how long the relevant segment
            # is), add a small lead-in for context, clamp to a sane range.
            clip_start = max(0, mention_time - _CLIP_LEAD_IN)
            raw_window = max(_CLIP_MIN_WINDOW, int(groq_end) - mention_time + _CLIP_LEAD_IN)
            clip_end   = clip_start + min(raw_window, _CLIP_MAX_WINDOW)
            embed_url = (
                f"https://www.youtube.com/embed/{video_id}"
                f"?start={clip_start}&end={clip_end}"
                f"&autoplay=0&rel=0&modestbranding=1"
            )

        original_text = (
            get_transcript_text_at(transcript, mention_time)
            if transcript else ""
        )
        # P1-3 fix: if the window-extract returned empty (e.g. mention_time
        # outside the available transcript span) but a transcript exists,
        # fall back to the first relevant chunk so the card preview is
        # never blank. For metadata-only paths, fall back to the video
        # description excerpt where available.
        if not original_text:
            if transcript:
                joined = " ".join(seg.get("text", "") for seg in transcript[:5])
                original_text = joined.strip()[:500]
            else:
                desc = (video.get("description") or "").strip()
                original_text = desc[:500]
        english_summary = clip_info["summary"]

        embedding: list[float] | None = None
        try:
            embedding = generate_embedding(english_summary[:512])
        except Exception:
            logger.warning("Embedding failed for clip in %s", video_id, exc_info=True)

        embedding_literal = (
            "CAST(:embedding AS vector)" if embedding else "NULL"
        )
        published_raw = video.get("published_at")
        published_dt: datetime | None = None
        if isinstance(published_raw, datetime):
            published_dt = published_raw
        elif isinstance(published_raw, str) and published_raw:
            try:
                published_dt = datetime.fromisoformat(
                    published_raw.replace("Z", "+00:00")
                )
            except ValueError:
                published_dt = None

        # Confidence reflects how trustworthy the timestamp is.
        # Captions/yt-dlp/Whisper = real timestamp; metadata-only = full-video link.
        source_confidence = {
            "captions": 0.95,
            "whisper":  0.85,
            "yt_dlp":   0.85,
            "metadata": 0.30,
        }.get(transcript_source or "metadata", 0.6)

        importance_score = {"high": 0.9, "medium": 0.6, "low": 0.3}.get(
            clip_info.get("importance", "medium"), 0.6
        )

        params = {
            "video_id":          video_id,
            "title":             video["title"],
            "channel_id":        channel_id,
            "channel_name":      video["channel_name"],
            "published_at":      published_dt,
            "video_url":         f"https://youtube.com/watch?v={video_id}",
            "start_secs":        clip_start,
            "end_secs":          clip_end,
            "embed_url":         embed_url,
            "transcript":        original_text,
            "lang":              lang,
            "translated":        english_summary,
            "entity":            clip_info["entity"],
            "relevance":         importance_score,
            "transcript_source": transcript_source or "metadata",
            "confidence":        source_confidence * importance_score,
        }
        if embedding:
            params["embedding"] = str(embedding)

        try:
            await db.execute(text("SAVEPOINT clip_sp"))
            await db.execute(
                text(f"""
                    INSERT INTO youtube_clips (
                        video_id, video_title, channel_id, channel_name,
                        video_published_at, video_url,
                        clip_start_seconds, clip_end_seconds, embed_url,
                        transcript_segment, transcript_language, transcript_translated,
                        matched_entity, labse_embedding, relevance_score, processed,
                        transcript_source, confidence
                    ) VALUES (
                        :video_id, :title, :channel_id, :channel_name,
                        :published_at, :video_url,
                        :start_secs, :end_secs, :embed_url,
                        :transcript, :lang, :translated,
                        :entity, {embedding_literal}, :relevance, TRUE,
                        :transcript_source, :confidence
                    )
                    ON CONFLICT (video_id, clip_start_seconds, matched_entity)
                    DO NOTHING
                """),
                params,
            )
            await db.execute(text("RELEASE SAVEPOINT clip_sp"))
            clips_created += 1
            logger.info(
                "Clip created: %s at %ds — entity: %s — importance: %s",
                video_id, clip_start, clip_info["entity"], clip_info["importance"],
            )
        except Exception:
            await db.execute(text("ROLLBACK TO SAVEPOINT clip_sp"))
            logger.warning("Clip insert failed for %s", video_id, exc_info=True)

    return clips_created
