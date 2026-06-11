"""Event-first clustering — build + validate in one script.

For each event in article_events (in a target window):
  1. Build a candidate set of existing clusters that overlap on actors
     AND have a canonical_date within ±N days.
  2. Score each candidate with a weighted sum of structured signals:
        - actor_jaccard       (35%)
        - date_proximity      (25% — 0..1 by gaussian decay)
        - event_type_match    (20%)
        - description_similarity via fuzzy ratio  (15%)
        - source_diversity_bonus  (5% — favors cross-source matches)
  3. If top score >= HARD_MATCH: auto-assign to that cluster
     If top score <= HARD_REJECT or no candidates: spawn new cluster
     Otherwise: (Phase 2 will call LLM judge — Phase 1 spawns conservatively)
  4. Update cluster's article_count, source_count, last_updated_at

Outputs:
  /tmp/event_validation/summary.json
  /tmp/event_validation/clusters.json
  /tmp/event_validation/articles_per_cluster.json

Usage (inside rig-backend):
  python3 /app/event_cluster_validate.py --since-days 5 --reset
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from collections import Counter
from datetime import datetime, date as date_cls
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402

from backend.database import get_db  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("event_cluster")

OUT_DIR = Path("/tmp/event_validation")
OUT_DIR.mkdir(exist_ok=True)

# --- Scoring config -------------------------------------------------------
DATE_WINDOW_DAYS = 3       # ± days for candidate retrieval
TOP_K = 10                  # candidates considered per new event
HARD_MATCH_SCORE = 0.78    # auto-assign threshold
HARD_REJECT_SCORE = 0.40   # auto-spawn threshold (below this → new cluster)
W_ACTOR = 0.35
W_DATE = 0.25
W_TYPE = 0.20
W_DESC = 0.15
W_SOURCE = 0.05
# ------------------------------------------------------------------------


def actor_jaccard(a: list[str] | None, b: list[str] | None) -> float:
    if not a or not b:
        return 0.0
    sa = {s.strip().lower() for s in a if s}
    sb = {s.strip().lower() for s in b if s}
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def date_proximity(da: date_cls | None, db: date_cls | None) -> float:
    if da is None or db is None:
        return 0.0
    diff_days = abs((da - db).days)
    if diff_days == 0:
        return 1.0
    return max(0.0, 1.0 - diff_days / (DATE_WINDOW_DAYS + 1))


def desc_ratio(a: str | None, b: str | None) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a.lower()[:200], b.lower()[:200]).ratio()


def score_match(new_event: dict, candidate: dict) -> float:
    aj = actor_jaccard(new_event.get("actors"), candidate.get("canonical_actors"))
    dp = date_proximity(new_event.get("event_date"), candidate.get("canonical_date"))
    tm = 1.0 if (new_event.get("event_type") and
                 new_event.get("event_type") == candidate.get("canonical_event_type")) else 0.0
    dr = desc_ratio(new_event.get("event_description"),
                    candidate.get("canonical_description"))
    src_bonus = 1.0 if new_event.get("source_id") not in (candidate.get("_sources") or set()) else 0.5
    return (W_ACTOR * aj + W_DATE * dp + W_TYPE * tm + W_DESC * dr + W_SOURCE * src_bonus)


# --- DB helpers ----------------------------------------------------------
async def reset_event_clusters(db) -> None:
    await db.execute(text("UPDATE article_events SET event_cluster_id = NULL WHERE event_cluster_id IS NOT NULL"))
    await db.execute(text("DELETE FROM event_clusters"))
    await db.commit()
    logger.info("Reset event_clusters table.")


async def fetch_events_to_cluster(db, since_days: int, limit: int | None) -> list[dict]:
    q = text("""
        SELECT
          ae.id::text          AS event_id,
          ae.article_id::text  AS article_id,
          ae.actors            AS actors,
          ae.event_type        AS event_type,
          ae.event_date        AS event_date,
          ae.event_description AS event_description,
          ae.is_future         AS is_future,
          a.source_id::text    AS source_id,
          s.name               AS source_name,
          a.title              AS article_title,
          a.collected_at       AS collected_at
        FROM article_events ae
        JOIN articles a ON a.id = ae.article_id
        JOIN sources s ON s.id = a.source_id
        WHERE a.collected_at > NOW() - make_interval(days => :d)
          AND ae.actors IS NOT NULL
          AND array_length(ae.actors, 1) > 0
          AND ae.event_date IS NOT NULL
          AND ae.event_description IS NOT NULL
        ORDER BY a.collected_at
    """ + ((" LIMIT " + str(int(limit))) if limit else ""))
    rows = await db.execute(q, {"d": since_days})
    return [dict(r._mapping) for r in rows.fetchall()]


async def find_candidates(db, ev: dict) -> list[dict]:
    """Return up to TOP_K existing clusters that overlap on actors and date."""
    from datetime import timedelta
    d = ev["event_date"]
    d_lo = d - timedelta(days=DATE_WINDOW_DAYS)
    d_hi = d + timedelta(days=DATE_WINDOW_DAYS)
    actors_list = list(ev["actors"] or [])
    q = text("""
        SELECT ec.id::text         AS id,
               ec.canonical_actors AS canonical_actors,
               ec.canonical_event_type AS canonical_event_type,
               ec.canonical_date   AS canonical_date,
               ec.canonical_description AS canonical_description,
               ec.article_count, ec.source_count
          FROM event_clusters ec
         WHERE ec.is_active
           AND ec.canonical_actors && :actors
           AND ec.canonical_date BETWEEN :d_lo AND :d_hi
         ORDER BY
            CASE WHEN ec.canonical_event_type = :etype THEN 0 ELSE 1 END,
            ec.canonical_date DESC
         LIMIT :k
    """)
    rows = await db.execute(
        q, {
            "actors": actors_list,
            "d_lo": d_lo,
            "d_hi": d_hi,
            "etype": ev.get("event_type") or "",
            "k": TOP_K,
        }
    )
    return [dict(r._mapping) for r in rows.fetchall()]


def _format_pg_text_array(items: list[str]) -> str:
    """Serialize Python list to Postgres text[] literal."""
    if not items:
        return "{}"
    return "{" + ",".join(
        '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"' for s in items if s
    ) + "}"


async def spawn_cluster(db, ev: dict) -> str:
    actors_list = list(ev["actors"] or [])
    r = await db.execute(
        text("""
            INSERT INTO event_clusters (
              canonical_description, canonical_actors, canonical_event_type,
              canonical_date, is_future, article_count, source_count, confidence_score
            ) VALUES (
              :desc, :actors, :etype, :d, :fut, 1, 1, :conf
            )
            RETURNING id::text AS id
        """),
        {
            "desc": (ev["event_description"] or "")[:500],
            "actors": actors_list,
            "etype": ev.get("event_type"),
            "d": ev["event_date"],
            "fut": bool(ev.get("is_future")),
            "conf": 1.0,
        },
    )
    cid = r.fetchone().id
    await db.execute(
        text("UPDATE article_events SET event_cluster_id = CAST(:c AS uuid) WHERE id = CAST(:e AS uuid)"),
        {"c": cid, "e": ev["event_id"]},
    )
    return cid


async def assign_to_cluster(db, ev: dict, cluster_id: str, score: float) -> None:
    # Merge actors into canonical_actors set
    existing = await db.execute(
        text("SELECT canonical_actors FROM event_clusters WHERE id = CAST(:c AS uuid)"),
        {"c": cluster_id},
    )
    row = existing.fetchone()
    existing_actors = set(row.canonical_actors or [])
    new_actors = existing_actors | set(ev["actors"] or [])

    actors_list = sorted(new_actors)
    await db.execute(
        text("""
            UPDATE event_clusters
               SET canonical_actors = :actors,
                   article_count    = (
                     SELECT COUNT(DISTINCT ae.article_id)
                       FROM article_events ae
                      WHERE ae.event_cluster_id = CAST(:c AS uuid)
                   ) + 1,
                   source_count = (
                     SELECT COUNT(DISTINCT a.source_id)
                       FROM article_events ae
                       JOIN articles a ON a.id = ae.article_id
                      WHERE ae.event_cluster_id = CAST(:c AS uuid)
                   ),
                   last_updated_at  = NOW(),
                   confidence_score = LEAST(1.0, COALESCE(confidence_score, :conf) * 0.5 + :conf * 0.5)
             WHERE id = CAST(:c AS uuid)
        """),
        {"actors": actors_list, "c": cluster_id, "conf": score},
    )
    await db.execute(
        text("UPDATE article_events SET event_cluster_id = CAST(:c AS uuid) WHERE id = CAST(:e AS uuid)"),
        {"c": cluster_id, "e": ev["event_id"]},
    )


# --- Main pipeline -------------------------------------------------------
async def run(args: argparse.Namespace) -> int:
    async with get_db() as db:
        if args.reset:
            await reset_event_clusters(db)

        events = await fetch_events_to_cluster(db, args.since_days, args.limit)
        logger.info("Fetched %d events from last %d days", len(events), args.since_days)

    assigned = 0
    spawned = 0
    skipped = 0
    t0 = time.time()
    last_report = t0

    for i, ev in enumerate(events):
        async with get_db() as db:
            candidates = await find_candidates(db, ev)
            scored = sorted(
                ((score_match(ev, c), c) for c in candidates),
                key=lambda kv: -kv[0],
            )

            if scored and scored[0][0] >= HARD_MATCH_SCORE:
                await assign_to_cluster(db, ev, scored[0][1]["id"], scored[0][0])
                assigned += 1
            else:
                # Phase 1: no LLM yet — anything below hard-match → spawn
                # (gray zone Phase 2 will pass to LLM judge)
                await spawn_cluster(db, ev)
                spawned += 1
            await db.commit()

        now = time.time()
        if now - last_report >= 5 or (i + 1) == len(events):
            rate = (i + 1) / max(now - t0, 1)
            eta = (len(events) - i - 1) / max(rate, 0.1) / 60
            logger.info("PROGRESS %d/%d · %.1f ev/sec · ETA %.1f min · assigned=%d spawned=%d",
                        i + 1, len(events), rate, eta, assigned, spawned)
            last_report = now

    duration = time.time() - t0
    logger.info("DONE in %.1f min · events=%d · assigned=%d · spawned=%d",
                duration / 60, len(events), assigned, spawned)

    # --- Pull facts for report ----------------------------------------------
    async with get_db() as db:
        rows = await db.execute(text("""
            SELECT ec.id::text AS id,
                   ec.canonical_description AS desc,
                   ec.canonical_actors AS actors,
                   ec.canonical_event_type AS etype,
                   ec.canonical_date::text AS d,
                   ec.article_count, ec.source_count, ec.confidence_score
              FROM event_clusters ec
              JOIN article_events ae ON ae.event_cluster_id = ec.id
              JOIN articles a ON a.id = ae.article_id
             WHERE a.collected_at > NOW() - make_interval(days => :d)
             GROUP BY ec.id
             ORDER BY ec.article_count DESC NULLS LAST, ec.last_updated_at DESC
             LIMIT 200
        """), {"d": args.since_days})
        cluster_facts = [dict(r._mapping) for r in rows.fetchall()]

        per_cluster: dict[str, list] = {}
        if cluster_facts:
            ids = [c["id"] for c in cluster_facts]
            rows2 = await db.execute(text("""
                SELECT ec.id::text AS cluster_id,
                       a.id::text AS article_id,
                       LEFT(a.title, 140) AS title,
                       a.language_detected AS lang,
                       s.name AS source,
                       LEFT(ae.event_description, 180) AS event_desc,
                       ae.event_date::text AS event_date,
                       ae.event_type AS event_type
                  FROM event_clusters ec
                  JOIN article_events ae ON ae.event_cluster_id = ec.id
                  JOIN articles a ON a.id = ae.article_id
                  JOIN sources s ON s.id = a.source_id
                 WHERE ec.id::text = ANY(CAST(:ids AS text[]))
                 ORDER BY ec.id, a.collected_at
            """), {"ids": ids})
            for r in rows2.fetchall():
                m = dict(r._mapping)
                per_cluster.setdefault(m["cluster_id"], []).append(m)

    summary = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "since_days": args.since_days,
        "events_total": len(events),
        "events_assigned": assigned,
        "events_spawned": spawned,
        "events_skipped": skipped,
        "duration_sec": round(duration, 1),
        "clusters_total": len(cluster_facts),
        "multi_article_clusters": sum(1 for c in cluster_facts if (c.get("article_count") or 0) > 1),
        "singletons": sum(1 for c in cluster_facts if (c.get("article_count") or 0) <= 1),
        "size_buckets": dict(
            Counter(
                ("1" if (c.get("article_count") or 0) <= 1 else
                 "2-3" if c["article_count"] <= 3 else
                 "4-10" if c["article_count"] <= 10 else
                 "11-50" if c["article_count"] <= 50 else "50+")
                for c in cluster_facts
            )
        ),
        "source_diversity": dict(
            Counter(
                ("1 source" if (c.get("source_count") or 0) <= 1 else
                 "2-3 sources" if c["source_count"] <= 3 else "4+ sources")
                for c in cluster_facts
            )
        ),
    }
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    (OUT_DIR / "clusters.json").write_text(json.dumps(cluster_facts, indent=2, default=str), encoding="utf-8")
    (OUT_DIR / "articles_per_cluster.json").write_text(json.dumps(per_cluster, indent=2, default=str), encoding="utf-8")

    logger.info("Wrote artifacts to %s", OUT_DIR)
    logger.info("SUMMARY: %s", json.dumps(summary, indent=2, default=str))
    return 0


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--since-days", type=int, default=5)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--reset", action="store_true",
                   help="WIPE event_clusters + clear FK on article_events before run")
    args = p.parse_args()
    sys.exit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
