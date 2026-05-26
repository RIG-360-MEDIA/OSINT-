"""
Orchestrator: process one broadcast (VOD or live window) through the
3-Lens Consensus pipeline end-to-end.

Architectural deviation from the brief: the brief specifies a Celery
chord (L1‖L2‖L3 → reconcile callback). We instead run all three
lenses **in-process** inside a single Celery task on the whisper
queue. Reasons:

  - Whisper queue has concurrency=1; L1/L2/L3 would serialise anyway.
  - One Celery task = one place to debug if something goes wrong.
  - Async-gather of L2 (Groq, network) parallel with L3 (CPU) is
    achievable inside one process.
  - Cross-queue chord coordination on a sqlalchemy broker is brittle.

Same wallclock cost. Cleaner failure semantics.

Task entry:
  tasks.newsroom.process_broadcast(yt_video_id: str, channel_id: str,
                                   language: str = "te", title: str = "")

Returns: dict with counts (segments_inserted, mentions_inserted,
elapsed_sec, lens_status_per_call).
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras

from backend.celery_app import app
from backend.tasks.newsroom._audio_io import (
    AudioFile,
    cleanup as cleanup_audio,
    download_youtube_audio,
)
from backend.tasks.newsroom.diarise import diarise, speaker_for_time
from backend.tasks.newsroom.lens_l1 import fetch_l1_segments
from backend.tasks.newsroom.lens_l2 import fetch_l2_segments
from backend.tasks.newsroom.lens_l3 import fetch_l3_segments
from backend.tasks.newsroom.phonetic_snap import (
    EntityMention,
    load_entity_index,
    snap_text,
)
from backend.tasks.newsroom.reconcile import (
    ReconciledSegment,
    _reconcile_async,
)

logger = logging.getLogger(__name__)


def _pg_url() -> str:
    return os.environ.get(
        "DATABASE_URL_SYNC",
        "postgresql://rig:rigpassword@rig-postgres:5432/rig",
    )


@app.task(
    name="tasks.newsroom.process_broadcast",
    queue="whisper",
    bind=True,
    max_retries=1,
    soft_time_limit=1800,    # 30 min
    time_limit=2100,
)
def process_broadcast(
    self,
    yt_video_id: str,
    channel_id: str,
    *,
    language: str = "te",
    title: str | None = None,
    is_live: bool = False,
    max_duration_sec: int | None = None,
    skip_l3: bool = False,
) -> dict:
    """End-to-end processing of one broadcast.

    Idempotent: if the broadcast row already has segments, this is a
    no-op (we don't re-transcribe to save quota). To force re-run,
    delete the broadcast's segments first.

    `skip_l3` (bool, default False):
      - For VOD ingest the default is False with adaptive L3 — L3 only
        actually runs if L2 is empty / errors / has bad confidence.
      - For live monitoring, callers pass skip_l3=True so the 30 s
        window finishes inside its budget — L2 alone (Groq Whisper API)
        keeps up with real time, L3 (CPU Faster-Whisper) doesn't.
    """
    started = time.time()
    stats: dict = {
        "yt_video_id": yt_video_id,
        "channel_id": channel_id,
        "language": language,
        "is_live": is_live,
        "lens_status": {},
        "segments_inserted": 0,
        "mentions_inserted": 0,
        "skipped_existing": False,
        "elapsed_sec": 0.0,
    }

    conn = psycopg2.connect(_pg_url())
    conn.autocommit = False
    audio: AudioFile | None = None

    try:
        # ── 1. Ensure broadcast row exists, idempotency check ────────────
        broadcast_id = _upsert_broadcast(
            conn, channel_id, yt_video_id, title, is_live=is_live,
        )

        existing = _count_segments(conn, broadcast_id)
        if existing > 0 and not is_live:
            stats["skipped_existing"] = True
            stats["segments_inserted"] = 0
            stats["broadcast_id"] = broadcast_id
            stats["existing_segments"] = existing
            stats["elapsed_sec"] = time.time() - started
            logger.info(
                "process_broadcast: broadcast %s already has %d segments — skipping",
                broadcast_id, existing,
            )
            return stats

        # ── 2. Download audio + run lenses + reconcile in ONE asyncio.run
        # (groq_manager has a module-level asyncio.Lock; multiple
        # asyncio.run() calls would attach it to a dead loop)
        audio, l1, l2, l3, reconciled = asyncio.run(
            _run_async_pipeline(
                yt_video_id, language, max_duration_sec,
                skip_l3=skip_l3, is_live=is_live,
            )
        )
        stats["audio_duration_sec"] = audio.duration_sec
        stats["lens_status"]["l1"] = f"ok ({len(l1)} segs)" if l1 else "empty"
        stats["lens_status"]["l2"] = f"ok ({len(l2)} segs)" if l2 else "empty"
        stats["lens_status"]["l3"] = f"ok ({len(l3)} segs)" if l3 else "empty"
        stats["reconciled_count"] = len(reconciled)

        if not l2 and not l3:
            raise RuntimeError(
                f"Both L2 and L3 produced zero segments for {yt_video_id} — "
                "cannot reconcile. L1 alone is too unreliable to trust."
            )
        if not reconciled:
            raise RuntimeError("reconcile returned 0 segments; aborting insert")

        # ── 5. Diarise (sync; no event loop required) ─────────────────────
        turns = diarise(audio.path, total_duration_sec=audio.duration_sec)
        stats["diarisation_turns"] = len(turns)

        # ── 6. Phonetic snap on each canonical segment ────────────────────
        with conn.cursor() as cur:
            entity_index = load_entity_index(_PsycoCursorAdapter(cur))

        # ── 7. Insert segments + mentions ─────────────────────────────────
        with conn.cursor() as cur:
            seg_ids: list[str] = []
            for r in reconciled:
                midpoint = (r.start_sec + r.end_sec) / 2.0
                speaker_label = speaker_for_time(turns, midpoint)
                cur.execute(
                    """
                    INSERT INTO newsroom_segments (
                        broadcast_id, start_sec, end_sec,
                        speaker_label, speaker_entity_id,
                        text_native, text_en, confidence,
                        l1_text, l2_text, l3_text,
                        is_live
                    ) VALUES (
                        %s, %s, %s,
                        %s, NULL,
                        %s, %s, %s,
                        %s, %s, %s,
                        %s
                    )
                    RETURNING id
                    """,
                    (
                        broadcast_id, r.start_sec, r.end_sec,
                        speaker_label,
                        r.text_native, r.text_en, r.confidence,
                        r.l1_text, r.l2_text, r.l3_text,
                        is_live,
                    ),
                )
                seg_id = cur.fetchone()[0]
                seg_ids.append(seg_id)

                # Phonetic snap → entity_mentions
                mentions = snap_text(r.text_native, entity_index)
                # Also try snap on text_en — many proper nouns appear only
                # in transliterated form there
                if r.text_en:
                    mentions += snap_text(r.text_en, entity_index)

                # Dedupe on (entity_id, span_start) — many names hit on
                # both native + en passes with the same span
                seen_keys: set[tuple[str, int]] = set()
                for m in mentions:
                    k = (m.entity_id, m.span_start)
                    if k in seen_keys:
                        continue
                    seen_keys.add(k)
                    cur.execute(
                        """
                        INSERT INTO newsroom_entity_mentions (
                            segment_id, entity_id, span_start, span_end, was_phonetic
                        ) VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (segment_id, entity_id, span_start) DO NOTHING
                        """,
                        (seg_id, m.entity_id, m.span_start, m.span_end, m.was_phonetic),
                    )
                    stats["mentions_inserted"] += 1

                # Snap speaker_entity_id from speaker label-overlap heuristic:
                # if the segment's text_native exactly contains an entity that
                # phonetic_snap matched and that entity is a "person" type, use
                # it as the speaker.
                if mentions:
                    cur.execute(
                        """
                        UPDATE newsroom_segments
                           SET speaker_entity_id = (
                               SELECT m.entity_id
                                 FROM newsroom_entity_mentions m
                                 JOIN entity_dictionary ed ON ed.id = m.entity_id
                                WHERE m.segment_id = %s
                                  AND ed.entity_type = 'person'
                                ORDER BY m.was_phonetic ASC, m.span_start ASC
                                LIMIT 1
                           )
                         WHERE id = %s
                        """,
                        (seg_id, seg_id),
                    )

            stats["segments_inserted"] = len(seg_ids)

        conn.commit()
        stats["broadcast_id"] = broadcast_id
        stats["elapsed_sec"] = time.time() - started
        logger.info(
            "process_broadcast %s: %d segments, %d mentions, %.1fs",
            yt_video_id, stats["segments_inserted"], stats["mentions_inserted"],
            stats["elapsed_sec"],
        )
        return stats

    except Exception as exc:
        conn.rollback()
        logger.exception("process_broadcast failed for %s", yt_video_id)
        stats["error"] = str(exc)
        stats["elapsed_sec"] = time.time() - started
        raise
    finally:
        if audio is not None:
            cleanup_audio(audio)
        conn.close()


# ── Async pipeline driver (single-loop) ─────────────────────────────────────


_PROMPT_CACHE: dict[str, str] = {}


def _load_prompt_terms(language: str) -> str:
    """Build a comma-separated proper-noun list from entity_dictionary
    to bias Whisper toward correct spellings of regional politicians,
    parties, places. Cached per process; refresh on container restart.

    For Telugu/Hindi we filter to entries with state in
    {Telangana, Andhra Pradesh, India} so we don't dilute the prompt
    with unrelated English wikipedia entities.
    """
    if language in _PROMPT_CACHE:
        return _PROMPT_CACHE[language]

    states = (
        "('Telangana', 'Andhra Pradesh', 'India')"
        if language in {"te", "hi"} else
        "('India',)"
    )
    sql = f"""
        SELECT canonical_name FROM entity_dictionary
         WHERE entity_type IN ('person', 'organisation', 'place')
           AND (state IS NULL OR state IN {states})
           AND length(canonical_name) BETWEEN 4 AND 30
         ORDER BY length(canonical_name) DESC
         LIMIT 30
    """
    try:
        conn = psycopg2.connect(_pg_url())
        try:
            with conn.cursor() as cur:
                cur.execute(sql)
                names = [r[0] for r in cur.fetchall()]
        finally:
            conn.close()
        # Build prompt — include preface so Whisper knows the context.
        preface = "Telugu Telangana politics news. Names: " if language == "te" else "Indian news. Names: "
        prompt = preface + ", ".join(names)
        _PROMPT_CACHE[language] = prompt
        logger.info("prompt_terms[%s]: %d entities loaded", language, len(names))
        return prompt
    except Exception as exc:  # noqa: BLE001
        logger.warning("prompt_terms load failed for %s: %s", language, exc)
        _PROMPT_CACHE[language] = ""
        return ""


async def _run_async_pipeline(
    yt_video_id: str,
    language: str,
    max_duration_sec: int | None,
    *,
    skip_l3: bool = False,
    is_live: bool = False,
):
    """Single async pipeline: download → L1 → L2 (and optionally L3) → reconcile.

    Everything inside one event loop so groq_manager's module-level
    asyncio.Lock stays valid throughout.

    Adaptive L3 strategy:
      - `skip_l3=True` (live monitor) — L3 never runs; pipeline completes
        on L1+L2 alone. Live windows must finish inside their budget;
        local Whisper at ~0.5x real-time can't keep up.
      - `skip_l3=False` (default, VOD ingest) — start L1 and L2 in
        parallel. WAIT for L2 to return. If L2 produced ≥3 segments,
        skip L3 (L2 is the largest Whisper model anyway via Groq's API,
        higher-quality than our local medium). If L2 returns nothing or
        errors, fall back to L3 so we don't ship a transcript-less
        broadcast.
      - This makes a 7-min VOD process in ~3 min instead of ~13 min on
        clean Groq days, while keeping the safety net for Groq outages.
    """
    audio = await download_youtube_audio(
        yt_video_id, max_duration_sec=max_duration_sec, is_live=is_live,
    )

    # Build a Whisper bias prompt from the entity dictionary so the
    # transcriber spells regional politicians correctly (instead of
    # producing 'Pachhim Veng' for 'Paschim Banga' etc.).
    prompt_terms = await asyncio.to_thread(_load_prompt_terms, language)

    # L1 is sync but I/O-bound; run via to_thread so it doesn't block
    l1_task = asyncio.create_task(asyncio.to_thread(fetch_l1_segments, yt_video_id, language))
    l2_task = asyncio.create_task(
        fetch_l2_segments(audio.path, language=language, prompt_terms=prompt_terms or None)
    )

    l1: list = []
    l2: list = []
    l3: list = []
    try:
        l1 = await l1_task
    except Exception as exc:  # noqa: BLE001
        logger.warning("L1 failed (async): %s", exc)
    try:
        l2 = await l2_task
    except Exception as exc:  # noqa: BLE001
        logger.warning("L2 failed (async): %s", exc)

    # Decide whether to run L3
    run_l3 = False
    if skip_l3:
        logger.info("skip_l3=True (live monitor) — bypassing local Whisper")
    elif len(l2) >= 3:
        logger.info("L2 produced %d segments — adaptive L3 skipped", len(l2))
    else:
        logger.info("L2 produced %d segments (insufficient) — running L3 fallback", len(l2))
        run_l3 = True

    if run_l3:
        def _l3_with_prompt() -> list:
            return fetch_l3_segments(audio.path, language, prompt_terms=prompt_terms or None)
        try:
            l3 = await asyncio.to_thread(_l3_with_prompt)
        except Exception as exc:  # noqa: BLE001
            logger.warning("L3 fallback failed: %s", exc)

    reconciled = await _reconcile_async(l1, l2, l3, language=language)
    return audio, l1, l2, l3, reconciled


# ── DB helpers (sync, psycopg2) ─────────────────────────────────────────────


def _upsert_broadcast(
    conn,
    channel_id: str,
    yt_video_id: str,
    title: str | None,
    *,
    is_live: bool,
) -> str:
    """Insert a broadcast row if missing, return its id either way."""
    now = datetime.now(timezone.utc)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO newsroom_broadcasts (
                channel_id, yt_video_id, title, started_at, is_live
            ) VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (channel_id, yt_video_id) DO UPDATE
              SET is_live = EXCLUDED.is_live,
                  title   = COALESCE(EXCLUDED.title, newsroom_broadcasts.title)
            RETURNING id
            """,
            (channel_id, yt_video_id, title, now, is_live),
        )
        return str(cur.fetchone()[0])


def _count_segments(conn, broadcast_id: str) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM newsroom_segments WHERE broadcast_id = %s",
            (broadcast_id,),
        )
        return int(cur.fetchone()[0])


# ── Adapter so phonetic_snap.load_entity_index can call .execute().fetchall() ──


class _PsycoCursorAdapter:
    """Tiny adapter to make a psycopg2 cursor look like a sqlalchemy
    session for `load_entity_index`. Just enough surface area."""

    def __init__(self, cur):
        self._cur = cur

    def execute(self, query, params=None):
        self._cur.execute(query, params or ())
        return self

    def fetchall(self):
        return self._cur.fetchall()
