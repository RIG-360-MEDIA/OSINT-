"""
Phase 5 — cross-channel breaking-event detection.

Every 2 minutes (Beat-driven), this task:

  1. Pulls all newsroom_segments from the last 20 minutes.
  2. Groups them by shared entity (newsroom_entity_mentions) — segments
     that mention the same entity are candidates for the same event.
  3. Filters candidate groups to those carried by ≥3 distinct channels.
     Lower-bar groups are ignored (single-channel chatter).
  4. For each remaining candidate, calls Cerebras (via call_groq's
     auto-failover) with a quality-gate prompt that returns:
         { headline, headline_en, is_real_event, severity (1..5) }
     The `is_real_event=False` filter weeds out coincidental mentions
     (e.g. three channels all running an unrelated KCR archival clip).
  5. Inserts newsroom_breaking_clusters + newsroom_breaking_segments.

Idempotency: a candidate group whose top-3 segments are already in a
breaking cluster row (by membership lookup) is skipped — re-runs are
safe and don't duplicate.

NOTE: distinct from the existing `breaking_clusters` table introduced
in migration 042 (Hetzner-only). That serves the /coverage hub from
articles; this serves THE NEWSROOM /clips wall from broadcast segments.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone

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


_WINDOW_MIN = 20
_MIN_CHANNELS = 3

_GATE_SYSTEM = (
    "You are a news quality-gate classifier. You receive 3-5 transcript "
    "snippets from different TV channels that all mention the same entity "
    "in the last 20 minutes. Decide whether they are reporting the SAME "
    "real-world event happening NOW.\n"
    "Output STRICT JSON only:\n"
    "  {\"headline\": str (in source language),\n"
    "   \"headline_en\": str (English),\n"
    "   \"is_real_event\": bool,\n"
    "   \"severity\": int 1-5 (1=routine, 5=top-of-bulletin breaking)}"
)


@app.task(
    name="tasks.newsroom.detect_breaking",
    queue="nlp",
    max_retries=1,
)
def detect_breaking() -> dict:
    """Run a single sweep over the last 20 minutes of segments."""
    conn = psycopg2.connect(_pg_url())
    conn.autocommit = False
    stats = {
        "segments_scanned": 0,
        "candidate_groups": 0,
        "clusters_inserted": 0,
        "clusters_filtered_out": 0,
    }

    try:
        cutoff = datetime.now(tz=timezone.utc) - timedelta(minutes=_WINDOW_MIN)

        # ── Pull segments + entities + channel info ───────────────────────
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT s.id        AS segment_id,
                       s.text_native,
                       s.text_en,
                       s.created_at,
                       b.channel_id,
                       em.entity_id
                  FROM newsroom_segments s
                  JOIN newsroom_broadcasts b   ON b.id  = s.broadcast_id
                  LEFT JOIN newsroom_entity_mentions em ON em.segment_id = s.id
                 WHERE s.created_at >= %s
                """,
                (cutoff,),
            )
            rows = cur.fetchall()
        stats["segments_scanned"] = len({r["segment_id"] for r in rows})

        # ── Group segment-ids by entity_id, also collect channels ─────────
        entity_to_segments: dict[str, set] = defaultdict(set)
        entity_to_channels: dict[str, set] = defaultdict(set)
        seg_meta: dict[str, dict] = {}
        for r in rows:
            seg_meta[r["segment_id"]] = {
                "text": r["text_en"] or r["text_native"] or "",
                "channel_id": r["channel_id"],
                "created_at": r["created_at"],
            }
            ent = r["entity_id"]
            if ent is None:
                continue
            entity_to_segments[ent].add(r["segment_id"])
            entity_to_channels[ent].add(r["channel_id"])

        # ── Candidate filter: ≥3 distinct channels ────────────────────────
        candidates: list[tuple[str, set[str]]] = []
        for ent, channels in entity_to_channels.items():
            if len(channels) >= _MIN_CHANNELS:
                candidates.append((ent, entity_to_segments[ent]))
        stats["candidate_groups"] = len(candidates)

        if not candidates:
            return stats

        # ── Skip candidates whose segments are already in a cluster ───────
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT bs.segment_id
                  FROM newsroom_breaking_segments bs
                  JOIN newsroom_breaking_clusters bc ON bc.id = bs.cluster_id
                 WHERE bc.last_seen_at >= %s
                """,
                (cutoff,),
            )
            already_clustered = {row[0] for row in cur.fetchall()}

        # ── Quality-gate each candidate ───────────────────────────────────
        for ent, seg_ids in candidates:
            unclustered = [s for s in seg_ids if s not in already_clustered]
            if len(unclustered) < _MIN_CHANNELS:
                continue
            # Use up to 5 representative snippets
            sample_ids = list(unclustered)[:5]
            samples = [seg_meta[sid]["text"][:300] for sid in sample_ids if seg_meta.get(sid)]
            if len(samples) < _MIN_CHANNELS:
                continue

            try:
                gate = asyncio.run(_quality_gate(samples))
            except (GroqCallFailed, GroqQuotaExhausted) as exc:
                logger.warning("detect_breaking: gate call failed: %s", exc)
                continue

            if not gate.get("is_real_event"):
                stats["clusters_filtered_out"] += 1
                continue

            severity = int(gate.get("severity") or 1)
            severity = max(1, min(5, severity))

            channels = {seg_meta[sid]["channel_id"] for sid in seg_ids if sid in seg_meta}
            first_seen = min(seg_meta[sid]["created_at"] for sid in seg_ids if sid in seg_meta)
            last_seen = max(seg_meta[sid]["created_at"] for sid in seg_ids if sid in seg_meta)

            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO newsroom_breaking_clusters (
                        headline, headline_en,
                        first_seen_at, last_seen_at,
                        channel_count, segment_count,
                        is_real_event, severity
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        gate.get("headline") or "",
                        gate.get("headline_en") or "",
                        first_seen, last_seen,
                        len(channels), len(seg_ids),
                        True, severity,
                    ),
                )
                cluster_id = cur.fetchone()[0]

                rows_to_insert = [(cluster_id, sid) for sid in seg_ids]
                psycopg2.extras.execute_values(
                    cur,
                    """
                    INSERT INTO newsroom_breaking_segments (cluster_id, segment_id)
                    VALUES %s
                    ON CONFLICT (cluster_id, segment_id) DO NOTHING
                    """,
                    rows_to_insert,
                )
            stats["clusters_inserted"] += 1

        conn.commit()
        return stats
    except Exception:
        conn.rollback()
        logger.exception("detect_breaking failed")
        raise
    finally:
        conn.close()


async def _quality_gate(samples: list[str]) -> dict:
    """Ask the LLM whether these snippets describe a real shared event."""
    user = (
        f"Snippets (one per line, from {len(samples)} different channels):\n"
        + "\n".join(f"- {s}" for s in samples)
        + "\nDecide if all snippets are reporting the same real-world event "
          "happening within the last 20 minutes. If they share an entity but "
          "describe unrelated stories (archive footage, generic profile), "
          "set is_real_event=false."
    )
    raw = await call_groq(
        system=_GATE_SYSTEM,
        user=user,
        task_type="brief_generation",
        json_response=True,
    )
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    return {"is_real_event": False}
