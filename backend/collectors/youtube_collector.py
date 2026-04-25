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

_CLIP_BEFORE = 15  # seconds before entity mention
_CLIP_AFTER  = 15  # seconds after entity mention
_MAX_TRANSCRIPT_CHARS = 6000  # chars sent to Groq per analysis call
_MAX_SEGMENTS_SAMPLED = 250   # max segments sampled per video

# Circuit breaker: once we see N consecutive IP blocks, skip transcript path entirely
_IP_BLOCK_THRESHOLD = 3
_ip_block_streak = 0

# API keys marked as quota-exhausted for this process run
_exhausted_api_keys: set[str] = set()


def _is_quota_error(resp_text: str) -> bool:
    return "quotaExceeded" in resp_text or "quota" in resp_text.lower()


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

async def fetch_channel_videos(
    channel_id: str,
    api_key: str | list[str],
    since_days: int = 2,
) -> list[dict]:
    """
    Fetch recent videos from a channel via YouTube Data API v3.

    Accepts either a single key or a list of keys. On HTTP 403 with quotaExceeded
    the current key is marked exhausted for the rest of the process and the next
    key is tried automatically.
    """
    since = datetime.now(timezone.utc) - timedelta(days=since_days)
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
            r = await _get(
                client,
                "https://www.googleapis.com/youtube/v3/search",
                {
                    "part":           "snippet",
                    "channelId":      channel_id,
                    "type":           "video",
                    "order":          "date",
                    "publishedAfter": published_after,
                    "maxResults":     10,
                },
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

async def analyze_transcript_with_groq(
    transcript: list[dict],
    video_title: str,
    channel_name: str,
    user_entities: list[str],
) -> list[dict]:
    """
    Send transcript to Groq for entity relevance analysis.

    Samples up to _MAX_SEGMENTS_SAMPLED segments uniformly across the video,
    formats as timestamped lines, and asks Groq to identify segments where
    monitored entities are mentioned and assess their intelligence value.

    Returns list of {entity, start_seconds, end_seconds, summary, importance}.
    Only medium and high importance clips are returned.
    """
    from backend.nlp.groq_client import FAST_MODEL, call_groq

    if not transcript or not user_entities:
        return []

    # Sample transcript uniformly to fit within token budget
    step = max(1, len(transcript) // _MAX_SEGMENTS_SAMPLED)
    sampled = transcript[::step][:_MAX_SEGMENTS_SAMPLED]

    lang = transcript[0].get("language", "en")
    lines = [f"[{int(seg['start'])}s] {seg['text'].strip()}" for seg in sampled]
    transcript_text = "\n".join(lines)[:_MAX_TRANSCRIPT_CHARS]

    entities_str = ", ".join(user_entities)

    system = (
        "You are a political intelligence analyst monitoring Telangana, India — "
        "government policy, politicians, political parties, and governance schemes. "
        f"Analyze this YouTube transcript from channel '{channel_name}'. "
        f"Identify any mentions of these monitored entities: {entities_str}. "
        "For each mention, assess whether it contains actionable intelligence "
        "(policy announcements, controversies, statements, events). "
        "\n\nCRITICAL ENTITY DISAMBIGUATION (Telugu/English speakers often abbreviate):\n"
        "- 'KCR' / 'కేసీఆర్' / 'Chandrashekar Rao' / 'KCR garu' = K. Chandrashekar Rao "
        "(senior — ex-CM, BRS founder). NEVER label as KTR.\n"
        "- 'KTR' / 'కేటీఆర్' / 'Tarakarama Rao' / 'Rama Rao' (son) = K.T. Rama Rao "
        "(working president, son of KCR). NEVER label as KCR.\n"
        "- 'Revanth' / 'రేవంత్' = A. Revanth Reddy (current CM, Congress). NOT KTR or KCR.\n"
        "- 'Harish' / 'హరీష్ రావు' = T. Harish Rao (BRS, nephew of KCR).\n"
        "- 'Uttam' = Uttam Kumar Reddy. 'Jagga Reddy' = T. Jagga Reddy.\n"
        "Use the EXACT canonical name from the entity list — pick ONLY the person actually "
        "mentioned in the transcript near the timestamp.\n\n"
        "Respond ONLY with valid JSON — no explanation, no markdown. "
        'Schema: {"clips": [{"entity": "exact entity name from list", '
        '"start_seconds": 120, "end_seconds": 150, '
        '"summary": "1-2 sentence English summary of what was said", '
        '"importance": "high|medium|low"}]} '
        "Omit low importance clips. If nothing relevant, return {\"clips\": []}."
    )

    user_msg = (
        f"Video title: {video_title}\n"
        f"Transcript language: {lang}\n\n"
        f"Transcript (format: [seconds] text):\n{transcript_text}"
    )

    try:
        raw = await call_groq(
            system=system,
            user=user_msg,
            task_type="transcript_analysis",
            model=FAST_MODEL,
            json_response=True,
        )

        data = json.loads(raw) if isinstance(raw, str) else raw
        clips = data.get("clips", [])

        # Build case-insensitive lookup to reject hallucinated entities
        entity_lookup = {e.lower(): e for e in user_entities}

        result = []
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
            result.append({
                "entity":        canonical,
                "start_seconds": start,
                "end_seconds":   end,
                "summary":       c["summary"],
                "importance":    c.get("importance", "medium"),
            })
        return result

    except Exception:
        logger.warning(
            "Groq transcript analysis failed for '%s'", video_title, exc_info=True
        )
        return []


async def analyze_video_metadata_with_groq(
    video_title: str,
    description: str,
    channel_name: str,
    user_entities: list[str],
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

    system = (
        "You are a political intelligence analyst monitoring Telangana, India. "
        f"Check if this YouTube video from '{channel_name}' is about any of these entities: {entities_str}. "
        "Flag videos where the entity appears in the title OR is a substantive topic in the description. "
        "Titles in Telugu/Hindi count too — translate mentally. "
        "\n\nCRITICAL DISAMBIGUATION:\n"
        "- 'KCR' / 'కేసీఆర్' / 'Chandrashekar Rao' = K. Chandrashekar Rao (ex-CM, BRS founder). NOT KTR.\n"
        "- 'KTR' / 'కేటీఆర్' / 'Rama Rao' (KCR's son) = K.T. Rama Rao (BRS working president). NOT KCR.\n"
        "- 'Revanth' / 'రేవంత్' = A. Revanth Reddy (current CM, Congress).\n"
        "- 'Harish' / 'హరీష్' = T. Harish Rao.\n"
        "Pick the EXACT canonical name of the person the title/description is actually about.\n\n"
        "Respond ONLY with valid JSON. "
        'Schema: {"clips": [{"entity": "exact entity name from my list", "start_seconds": 0, "end_seconds": 30, '
        '"summary": "1-2 sentence English summary of what the video covers about this entity", '
        '"importance": "high|medium|low"}]} '
        'If no relevant entity, return {"clips": []}.'
    )

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

    transcript = await fetch_transcript(video_id)

    # If youtube-transcript-api failed (IP block / no captions), try yt-dlp fallback
    if not transcript:
        transcript = await _fetch_transcript_ytdlp(video_id)
        if transcript:
            logger.info("yt-dlp transcript fetched for %s (%d segs)", video_id, len(transcript))

    if transcript:
        clips_from_groq = await analyze_transcript_with_groq(
            transcript=transcript,
            video_title=video["title"],
            channel_name=video["channel_name"],
            user_entities=user_entities,
        )
        lang = transcript[0].get("language", "en")
    else:
        # Transcript unavailable (IP block, no captions) — fall back to title+description
        logger.info("No transcript for %s — using metadata analysis", video_id)
        clips_from_groq = await analyze_video_metadata_with_groq(
            video_title=video["title"],
            description=video.get("description", ""),
            channel_name=video["channel_name"],
            user_entities=user_entities,
        )
        lang = "en"

    if not clips_from_groq:
        logger.info("No relevant clips found in %s", video_id)
        return 0
    clips_created = 0

    for clip_info in clips_from_groq:
        mention_time     = clip_info["start_seconds"]
        metadata_only    = clip_info.get("metadata_only", False)
        clip_start       = max(0, mention_time - _CLIP_BEFORE)
        clip_end         = mention_time + _CLIP_AFTER

        if metadata_only:
            # No transcript: link to full video (no start/end params)
            embed_url = (
                f"https://www.youtube.com/embed/{video_id}"
                f"?autoplay=0&rel=0&modestbranding=1"
            )
        else:
            embed_url = (
                f"https://www.youtube.com/embed/{video_id}"
                f"?start={clip_start}&end={clip_end}"
                f"&autoplay=0&rel=0&modestbranding=1"
            )

        original_text   = get_transcript_text_at(transcript, mention_time) if transcript else ""
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

        params = {
            "video_id":     video_id,
            "title":        video["title"],
            "channel_id":   channel_id,
            "channel_name": video["channel_name"],
            "published_at": published_dt,
            "video_url":    f"https://youtube.com/watch?v={video_id}",
            "start_secs":   clip_start,
            "end_secs":     clip_end,
            "embed_url":    embed_url,
            "transcript":   original_text,
            "lang":         lang,
            "translated":   english_summary,
            "entity":       clip_info["entity"],
            "relevance":    {"high": 0.9, "medium": 0.6, "low": 0.3}.get(
                clip_info.get("importance", "medium"), 0.6
            ),
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
                        matched_entity, labse_embedding, relevance_score, processed
                    ) VALUES (
                        :video_id, :title, :channel_id, :channel_name,
                        :published_at, :video_url,
                        :start_secs, :end_secs, :embed_url,
                        :transcript, :lang, :translated,
                        :entity, {embedding_literal}, :relevance, TRUE
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
