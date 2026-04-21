"""
YouTube channel monitor and transcript processor.

Flow per channel:
  1. List recent videos via YouTube Data API v3
  2. For each new video: fetch timestamped transcript
  3. Merge segments into 300-char overlapping chunks
  4. Scan chunks for user entity mentions (alias-aware)
  5. For each match: build 30s clip window, store record, embed transcript
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_CLIP_BEFORE = 15  # seconds before entity mention
_CLIP_AFTER  = 15  # seconds after entity mention
_CHUNK_SIZE  = 300  # chars per transcript chunk
_CHUNK_OVERLAP = 50  # overlap chars between chunks


# ── Channel video listing ─────────────────────────────────────────────────────

async def fetch_channel_videos(
    channel_id: str,
    api_key: str,
    since_days: int = 2,
) -> list[dict]:
    """Fetch recent videos from a channel via YouTube Data API v3."""
    since = datetime.now(timezone.utc) - timedelta(days=since_days)
    published_after = since.strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                "https://www.googleapis.com/youtube/v3/search",
                params={
                    "part":           "snippet",
                    "channelId":      channel_id,
                    "type":           "video",
                    "order":          "date",
                    "publishedAfter": published_after,
                    "maxResults":     20,
                    "key":            api_key,
                },
                timeout=15,
            )
            if r.status_code != 200:
                logger.warning(
                    "YouTube API %s for channel %s: %s",
                    r.status_code, channel_id, r.text[:200],
                )
                return []

            items = r.json().get("items", [])
            return [
                {
                    "video_id":      item["id"]["videoId"],
                    "title":         item["snippet"]["title"],
                    "published_at":  item["snippet"]["publishedAt"],
                    "channel_name":  item["snippet"]["channelTitle"],
                }
                for item in items
                if item.get("id", {}).get("videoId")
            ]
    except Exception:
        logger.exception("Channel video fetch failed for %s", channel_id)
        return []


# ── Transcript fetching ───────────────────────────────────────────────────────

async def fetch_transcript(video_id: str) -> list[dict] | None:
    """
    Fetch timestamped transcript for a public YouTube video.

    Returns list of {text, start, duration, language}.
    Tries youtube-transcript-api first (no API key), falls back to yt-dlp.
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        from youtube_transcript_api._errors import (
            NoTranscriptFound,
            TranscriptsDisabled,
        )

        try:
            api = YouTubeTranscriptApi()

            # Try preferred languages in order; api.fetch raises on failure
            lang = "en"
            data = None
            for try_lang in ["en", "te", "hi", "kn", "ta"]:
                try:
                    fetched = api.fetch(video_id, languages=[try_lang])
                    data = fetched
                    lang = try_lang
                    break
                except Exception:
                    continue

            # Fall back to any available language
            if data is None:
                transcript_list = api.list(video_id)
                for t in transcript_list:
                    fetched = api.fetch(video_id, languages=[t.language_code])
                    data = fetched
                    lang = t.language_code
                    break

            if data is None:
                raise NoTranscriptFound(video_id, [], {})  # type: ignore[arg-type]

            return [
                {
                    "text":     item.text,
                    "start":    item.start,
                    "duration": item.duration,
                    "language": lang,
                }
                for item in data
            ]

        except (TranscriptsDisabled, NoTranscriptFound):
            logger.info("No transcript via API for %s — trying yt-dlp", video_id)
            return await _fetch_transcript_ytdlp(video_id)

    except Exception:
        logger.warning("Transcript fetch failed for %s", video_id, exc_info=True)
        return None


async def _fetch_transcript_ytdlp(video_id: str) -> list[dict] | None:
    """Fallback: extract subtitles via yt-dlp (no video download)."""
    try:
        import json
        import os
        import tempfile

        import yt_dlp

        url = f"https://youtube.com/watch?v={video_id}"

        with tempfile.TemporaryDirectory() as tmpdir:
            ydl_opts = {
                "writesubtitles":    True,
                "writeautomaticsub": True,
                "subtitleslangs":    ["en", "te", "hi"],
                "skip_download":     True,
                "outtmpl":           f"{tmpdir}/%(id)s",
                "quiet":             True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            for lang in ["en", "te", "hi"]:
                vtt_path = f"{tmpdir}/{video_id}.{lang}.vtt"
                if os.path.exists(vtt_path):
                    return _parse_vtt(vtt_path, lang)

        return None
    except Exception:
        logger.warning("yt-dlp transcript failed for %s", video_id, exc_info=True)
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


# ── Transcript chunking ───────────────────────────────────────────────────────

def build_transcript_chunks(
    transcript: list[dict],
    chunk_size: int = _CHUNK_SIZE,
    overlap: int = _CHUNK_OVERLAP,
) -> list[dict]:
    """
    Merge transcript segments into overlapping chunks.

    Each chunk carries {text, start_seconds, end_seconds, language}.
    300-char chunks with 50-char overlap give precise timestamp mapping
    while staying well above LaBSE's 50-char minimum.
    """
    if not transcript:
        return []

    chunks: list[dict] = []
    current_text  = ""
    current_start = transcript[0]["start"]
    current_end   = current_start

    for segment in transcript:
        seg_text  = segment["text"].strip()
        seg_start = segment["start"]
        seg_end   = seg_start + segment.get("duration", 2.0)
        lang      = segment.get("language", "en")

        if len(current_text) + len(seg_text) + 1 < chunk_size:
            current_text += " " + seg_text if current_text else seg_text
            current_end   = seg_end
        else:
            if current_text.strip():
                chunks.append({
                    "text":          current_text.strip(),
                    "start_seconds": current_start,
                    "end_seconds":   current_end,
                    "language":      lang,
                })
            # Start next chunk with overlap from tail of current
            tail = current_text[-overlap:] if len(current_text) > overlap else current_text
            current_text  = (tail + " " + seg_text).strip()
            current_start = seg_start
            current_end   = seg_end

    if current_text.strip():
        chunks.append({
            "text":          current_text.strip(),
            "start_seconds": current_start,
            "end_seconds":   current_end,
            "language":      transcript[-1].get("language", "en"),
        })

    return chunks


# ── Entity detection ──────────────────────────────────────────────────────────

def detect_entities_in_chunks(
    chunks: list[dict],
    user_entities: list[str],
    entity_dictionary: dict,
) -> list[dict]:
    """
    Scan transcript chunks for entity mentions.

    Uses direct substring match + alias expansion from _ENTITY_DICT.
    Returns new chunk dicts (immutable — does not modify inputs) with
    matched_entity key added.
    """
    matched: list[dict] = []

    for chunk in chunks:
        text_lower = chunk["text"].lower()

        for entity_name in user_entities:
            found = False

            # Direct match on canonical name
            if entity_name.lower() in text_lower:
                found = True

            # Alias match via entity dictionary
            if not found:
                entry = entity_dictionary.get(entity_name.lower(), {})
                for alias in entry.get("aliases", []):
                    if alias.lower() in text_lower:
                        found = True
                        break

            if found:
                matched.append({**chunk, "matched_entity": entity_name})
                break  # one entity match per chunk is enough

    return matched


# ── Single-video processing ───────────────────────────────────────────────────

async def process_video(
    video: dict,
    channel_id: str,
    user_entities: list[str],
    entity_dictionary: dict,
    db,
) -> int:
    """
    Fetch transcript for a video, detect entity mentions, store clips.

    Returns number of clip records created.
    """
    from sqlalchemy import text

    from backend.nlp.nlp_embedding import generate_embedding

    video_id = video["video_id"]

    # Skip if already processed
    existing = await db.execute(
        text("SELECT COUNT(*) AS cnt FROM youtube_clips WHERE video_id = :vid"),
        {"vid": video_id},
    )
    if existing.fetchone().cnt > 0:
        logger.debug("Video %s already processed — skipping", video_id)
        return 0

    transcript = await fetch_transcript(video_id)
    if not transcript:
        logger.info("No transcript for %s", video_id)
        return 0

    chunks  = build_transcript_chunks(transcript)
    matched = detect_entities_in_chunks(chunks, user_entities, entity_dictionary)
    clips_created = 0

    for chunk in matched:
        mention_time = int(chunk["start_seconds"])
        clip_start   = max(0, mention_time - _CLIP_BEFORE)
        clip_end     = mention_time + _CLIP_AFTER

        embed_url = (
            f"https://www.youtube.com/embed/{video_id}"
            f"?start={clip_start}&end={clip_end}"
            f"&autoplay=0&rel=0&modestbranding=1"
        )

        # Translate non-English segments for embedding
        text_for_embedding = chunk["text"]
        translated_text: str | None = None

        if chunk.get("language") not in ("en", None):
            try:
                from backend.nlp.nlp_language import translate_to_english
                translated_text    = await translate_to_english(chunk["text"])
                text_for_embedding = translated_text
            except Exception:
                logger.warning("Translation failed for clip in %s", video_id, exc_info=True)

        # Generate LaBSE embedding
        embedding: list[float] | None = None
        try:
            embedding = generate_embedding(text_for_embedding[:512])
        except Exception:
            logger.warning("Embedding failed for clip in %s", video_id, exc_info=True)

        try:
            await db.execute(
                text("""
                    INSERT INTO youtube_clips (
                        video_id, video_title, channel_id, channel_name,
                        video_published_at, video_url,
                        clip_start_seconds, clip_end_seconds, embed_url,
                        transcript_segment, transcript_language, transcript_translated,
                        matched_entity, labse_embedding, processed
                    ) VALUES (
                        :video_id, :title, :channel_id, :channel_name,
                        :published_at::timestamptz, :video_url,
                        :start_secs, :end_secs, :embed_url,
                        :transcript, :lang, :translated,
                        :entity, :embedding::vector, TRUE
                    )
                    ON CONFLICT (video_id, clip_start_seconds, matched_entity)
                    DO NOTHING
                """),
                {
                    "video_id":    video_id,
                    "title":       video["title"],
                    "channel_id":  channel_id,
                    "channel_name": video["channel_name"],
                    "published_at": video.get("published_at"),
                    "video_url":   f"https://youtube.com/watch?v={video_id}",
                    "start_secs":  clip_start,
                    "end_secs":    clip_end,
                    "embed_url":   embed_url,
                    "transcript":  chunk["text"],
                    "lang":        chunk.get("language", "en"),
                    "translated":  translated_text,
                    "entity":      chunk["matched_entity"],
                    "embedding":   str(embedding) if embedding else None,
                },
            )
            clips_created += 1
            logger.info(
                "Clip created: %s at %ds — entity: %s",
                video_id, clip_start, chunk["matched_entity"],
            )
        except Exception:
            logger.warning("Clip insert failed for %s", video_id, exc_info=True)

    return clips_created
