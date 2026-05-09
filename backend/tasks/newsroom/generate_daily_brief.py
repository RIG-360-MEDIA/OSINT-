"""
Phase 8 — Daily NEWSROOM digest.

Beat-driven 06:00 IST (00:30 UTC).

Pulls the prior calendar day's broadcast segments, picks 5–7 anchor
stories (highest cross-channel carry × highest segment count × top
quotes), and asks Cerebras (via call_groq's auto-failover) to write
a headline + 2-paragraph summary per story citing source segments.

Output: one row in newsroom_briefs keyed on the IST date. Idempotent —
re-running on the same date overwrites rather than duplicating.

TTS narration (audio) is deferred to v2; v1 ships text-only.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone

import psycopg2
import psycopg2.extras

from backend.celery_app import app
from backend.nlp.groq_client import call_groq, GroqCallFailed, GroqQuotaExhausted

logger = logging.getLogger(__name__)


def _pg_url() -> str:
    return os.environ.get(
        "DATABASE_URL_SYNC",
        "postgresql://rig:rigpassword@rig-postgres:5432/rig",
    )


_IST = timezone(timedelta(hours=5, minutes=30))
_TARGET_STORY_COUNT = 6


_BRIEF_SYSTEM = (
    "You are an editor composing a 5–7 story morning intelligence brief "
    "from yesterday's TV/YouTube transcripts. For each anchor story:\n"
    "  - headline (≤80 chars, source language acceptable)\n"
    "  - summary (2 short paragraphs, English, citing what was said)\n"
    "Do NOT speculate beyond what the transcripts contain. Output STRICT "
    "JSON only — no prose, no markdown."
)


@app.task(
    name="tasks.newsroom.generate_daily_brief",
    queue="brief",
    max_retries=2,
)
def generate_daily_brief(for_date_iso: str | None = None) -> dict:
    """Generate a digest for `for_date_iso` (defaults to yesterday IST)."""
    if for_date_iso:
        for_date = date.fromisoformat(for_date_iso)
    else:
        # Default: yesterday in IST (matches the user's intel cycle)
        now_ist = datetime.now(tz=_IST)
        for_date = (now_ist - timedelta(days=1)).date()

    conn = psycopg2.connect(_pg_url())
    conn.autocommit = False
    stats = {
        "for_date":             for_date.isoformat(),
        "candidate_clusters":   0,
        "stories_generated":    0,
        "source_segment_count": 0,
        "source_channel_count": 0,
    }

    try:
        # Convert IST date to UTC range
        start_ist = datetime.combine(for_date, datetime.min.time(), tzinfo=_IST)
        end_ist   = start_ist + timedelta(days=1)
        start_utc = start_ist.astimezone(timezone.utc)
        end_utc   = end_ist.astimezone(timezone.utc)

        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT s.id::text          AS segment_id,
                       s.text_native, s.text_en,
                       s.is_quote, s.framing,
                       c.id::text          AS channel_id,
                       c.name              AS channel_name,
                       em.entity_id::text  AS entity_id,
                       ed.canonical_name   AS entity_name
                  FROM newsroom_segments s
                  JOIN newsroom_broadcasts b ON b.id = s.broadcast_id
                  JOIN newsroom_channels c   ON c.id = b.channel_id
                  LEFT JOIN newsroom_entity_mentions em ON em.segment_id = s.id
                  LEFT JOIN entity_dictionary ed        ON ed.id = em.entity_id
                 WHERE s.created_at >= %s AND s.created_at < %s
                """,
                (start_utc, end_utc),
            )
            rows = cur.fetchall()

        if not rows:
            logger.info("generate_daily_brief: no segments for %s; skipping", for_date)
            return stats

        stats["source_segment_count"] = len({r["segment_id"] for r in rows})
        stats["source_channel_count"] = len({r["channel_id"] for r in rows})

        # Build entity-keyed clusters
        ent_to_segs: dict[str, list[dict]] = defaultdict(list)
        ent_to_channels: dict[str, set[str]] = defaultdict(set)
        for r in rows:
            if not r["entity_id"]:
                continue
            ent_to_segs[r["entity_id"]].append(r)
            ent_to_channels[r["entity_id"]].add(r["channel_id"])

        # Rank candidate entities: cross-channel carry × segment count × quote share
        scored: list[tuple[str, float, list[dict]]] = []
        for ent_id, segs in ent_to_segs.items():
            chans = ent_to_channels[ent_id]
            if len(segs) < 3:
                continue
            quote_share = sum(1 for s in segs if s["is_quote"]) / max(1, len(segs))
            score = len(chans) * 1.5 + len(segs) * 0.4 + quote_share * 2.0
            scored.append((ent_id, score, segs))
        scored.sort(key=lambda t: t[1], reverse=True)
        top = scored[: _TARGET_STORY_COUNT + 1]
        stats["candidate_clusters"] = len(top)
        if not top:
            logger.info("generate_daily_brief: no qualifying clusters for %s", for_date)
            return stats

        # Build the LLM prompt
        items = []
        for ent_id, score, segs in top:
            samples = [
                {
                    "segment_id": s["segment_id"],
                    "channel":    s["channel_name"],
                    "is_quote":   bool(s["is_quote"]),
                    "framing":    s["framing"],
                    "text":       (s["text_en"] or s["text_native"] or "")[:300],
                }
                for s in segs[:6]
            ]
            entity_name = next((s["entity_name"] for s in segs if s.get("entity_name")), "Unknown")
            items.append({
                "entity":  entity_name,
                "samples": samples,
            })

        try:
            stories = asyncio.run(_compose_brief(items))
        except (GroqQuotaExhausted, GroqCallFailed) as exc:
            logger.warning("generate_daily_brief: LLM call failed: %s", exc)
            return stats

        stats["stories_generated"] = len(stories)
        if not stories:
            return stats

        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO newsroom_briefs (
                    for_date, generated_at, stories,
                    story_count, source_channel_count, source_segment_count
                ) VALUES (%s, NOW(), %s, %s, %s, %s)
                ON CONFLICT (for_date) DO UPDATE
                  SET generated_at         = NOW(),
                      stories              = EXCLUDED.stories,
                      story_count          = EXCLUDED.story_count,
                      source_channel_count = EXCLUDED.source_channel_count,
                      source_segment_count = EXCLUDED.source_segment_count
                """,
                (
                    for_date,
                    json.dumps(stories, ensure_ascii=False),
                    len(stories),
                    stats["source_channel_count"],
                    stats["source_segment_count"],
                ),
            )
        conn.commit()
        return stats

    except Exception:
        conn.rollback()
        logger.exception("generate_daily_brief failed")
        raise
    finally:
        conn.close()


async def _compose_brief(items: list[dict]) -> list[dict]:
    """Single-call composition: feed top entity clusters, get back stories list."""
    user = (
        "Write a brief for yesterday based on these entity-clustered TV "
        "transcript snippets. Pick 5-7 of the strongest clusters; skip "
        "weak/overlapping ones. Output:\n"
        "  {\"stories\": [\n"
        "    {\"headline\": str, \"summary\": str, "
        "\"source_segment_ids\": [str,...]},\n"
        "    ...\n"
        "  ]}\n\n"
        f"Clusters:\n{json.dumps(items, ensure_ascii=False)}"
    )
    raw = await call_groq(
        system=_BRIEF_SYSTEM,
        user=user,
        task_type="brief_generation",
        json_response=True,
    )
    try:
        parsed = json.loads(raw)
        stories = parsed.get("stories") if isinstance(parsed, dict) else None
        if isinstance(stories, list):
            return stories[:7]
    except json.JSONDecodeError:
        logger.warning("generate_daily_brief: LLM returned non-JSON")
    return []
