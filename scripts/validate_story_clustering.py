"""Validate the new story_clustering pipeline on a real corpus sample.

Runs INSIDE rig-backend container. Picks 500 articles from May 10-13
(dense enrichment window), clears their thread_id, re-clusters via the
new pipeline, then writes a manual-review JSON report.

Safety:
  * Saves the ORIGINAL thread_id mapping to a backup JSON so we can
    restore if the result is bad.
  * Only touches the 500 test articles.
  * v1 threads themselves are untouched (read-only).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import sys
import time
from collections import Counter
from datetime import date, datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("validate")

# Add /app to path so `backend.*` imports resolve when running with `python ...`
sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402

from backend.database import get_db  # noqa: E402
from backend.nlp.story_clustering import cluster_article  # noqa: E402


SAMPLE_SIZE = int(os.environ.get("SAMPLE_SIZE", "500"))
DATE_WINDOW_START = os.environ.get("DATE_START", "2026-05-10")
DATE_WINDOW_END = os.environ.get("DATE_END", "2026-05-13")
OUT_DIR = Path("/tmp/cluster_validation")
OUT_DIR.mkdir(exist_ok=True)


async def _pick_articles(db, n: int) -> list[dict]:
    rows = await db.execute(
        text(
            """
            SELECT
              a.id::text                AS id,
              a.title                   AS title,
              a.thread_id::text         AS old_thread_id,
              s.name                    AS source,
              a.language_detected       AS lang
            FROM articles a
            JOIN sources s ON s.id = a.source_id
            WHERE a.published_at::date BETWEEN CAST(:d1 AS date) AND CAST(:d2 AS date)
              AND a.labse_embedding IS NOT NULL
              AND length(coalesce(a.summary_executive,'')) > 120
              AND (s.name ILIKE '%telangana%' OR s.name ILIKE '%telugu%'
                   OR s.name ILIKE '%hyderabad%' OR s.name = 'The Hindu — Andhra Pradesh'
                   OR s.name ILIKE '%eenadu%' OR s.name ILIKE '%sakshi%'
                   OR s.name ILIKE '%namasthe%' OR s.name ILIKE '%v6%'
                   OR s.name ILIKE '%hmtv%' OR s.name ILIKE '%tv9%'
                   OR s.name ILIKE '%ntv%' OR s.name ILIKE '%mana telangana%'
                   OR s.name = 'Siasat Daily' OR s.name = 'Telugu 360')
            ORDER BY md5(a.id::text || 'val-v1-salt')
            LIMIT :n
            """
        ),
        {"d1": date.fromisoformat(DATE_WINDOW_START), "d2": date.fromisoformat(DATE_WINDOW_END), "n": n},
    )
    return [dict(r._mapping) for r in rows.fetchall()]


async def _clear_thread_ids(db, article_ids: list[str]) -> None:
    await db.execute(
        text("UPDATE articles SET thread_id = NULL WHERE id = ANY(CAST(:ids AS uuid[]))"),
        {"ids": article_ids},
    )


async def _gather_cluster_facts(db, thread_ids: list[str]) -> list[dict]:
    rows = await db.execute(
        text(
            """
            WITH ids AS (SELECT unnest(CAST(:ids AS uuid[])) AS id)
            SELECT
              st.id::text                       AS thread_id,
              st.title                          AS title,
              st.primary_entities               AS primary_entities,
              st.article_count                  AS article_count,
              st.source_count                   AS source_count,
              st.momentum                       AS momentum,
              st.confidence_score               AS confidence,
              st.seed_article_id::text          AS seed_article_id
            FROM ids
            JOIN story_threads st ON st.id = ids.id
            """
        ),
        {"ids": list(set(thread_ids))},
    )
    return [dict(r._mapping) for r in rows.fetchall()]


async def _articles_per_thread(db, thread_ids: list[str]) -> dict[str, list[dict]]:
    rows = await db.execute(
        text(
            """
            SELECT
              a.id::text                   AS id,
              a.thread_id::text            AS thread_id,
              a.title                      AS title,
              a.primary_subject            AS subject,
              a.language_detected          AS lang,
              s.name                       AS source
            FROM articles a
            JOIN sources s ON s.id = a.source_id
            WHERE a.thread_id = ANY(CAST(:ids AS uuid[]))
            ORDER BY a.thread_id, a.collected_at
            """
        ),
        {"ids": list(set(thread_ids))},
    )
    out: dict[str, list[dict]] = {}
    for r in rows.fetchall():
        out.setdefault(r.thread_id, []).append({
            "id": r.id, "title": r.title, "subject": r.subject,
            "lang": r.lang, "source": r.source,
        })
    return out


async def main() -> None:
    t0 = time.time()
    async with get_db() as db:
        logger.info("Picking %d articles from %s..%s", SAMPLE_SIZE, DATE_WINDOW_START, DATE_WINDOW_END)
        articles = await _pick_articles(db, SAMPLE_SIZE)
        logger.info("Got %d articles", len(articles))

        backup = {a["id"]: a["old_thread_id"] for a in articles}
        (OUT_DIR / "backup_thread_ids.json").write_text(json.dumps(backup), encoding="utf-8")

        article_ids = [a["id"] for a in articles]
        await _clear_thread_ids(db, article_ids)
        await db.commit()
        logger.info("Cleared thread_id for %d articles (originals backed up)", len(article_ids))

    # Cluster each article via the new pipeline (separate sessions per call)
    assignments: list[dict] = []
    t1 = time.time()
    spawned = assigned = skipped = errors = llm_used = 0
    for i, aid in enumerate(article_ids):
        try:
            async with get_db() as db:
                result = await cluster_article(aid, db)
                await db.commit()
            if result is None:
                skipped += 1
                assignments.append({"article_id": aid, "result": "skipped"})
                continue
            spawned += int(result.spawned_new)
            assigned += int(not result.spawned_new)
            llm_used += int(not result.skipped_llm)
            assignments.append({
                "article_id": aid,
                "thread_id": result.thread_id,
                "spawned_new": result.spawned_new,
                "skipped_llm": result.skipped_llm,
                "confidence": result.confidence,
                "distance": result.distance_to_seed,
            })
        except Exception as exc:  # pragma: no cover (logged + counted)
            logger.exception("article %s failed", aid)
            errors += 1
            assignments.append({"article_id": aid, "result": "error", "error": str(exc)[:200]})
        if (i + 1) % 50 == 0:
            logger.info("...processed %d/%d (elapsed %.1fs)", i + 1, len(article_ids), time.time() - t1)
    duration = time.time() - t1
    logger.info(
        "Clustering done in %.1fs — assigned=%d spawned=%d skipped=%d errors=%d llm_calls=%d",
        duration, assigned, spawned, skipped, errors, llm_used,
    )

    # Gather facts about the resulting clusters
    thread_ids = [a["thread_id"] for a in assignments if a.get("thread_id")]
    async with get_db() as db:
        cluster_facts = await _gather_cluster_facts(db, thread_ids)
        per_thread_articles = await _articles_per_thread(db, thread_ids)

    # Summary
    size_buckets = Counter()
    for f in cluster_facts:
        n = f["article_count"]
        if n == 1: size_buckets["1 (singleton)"] += 1
        elif n <= 3: size_buckets["2-3"] += 1
        elif n <= 10: size_buckets["4-10"] += 1
        elif n <= 50: size_buckets["11-50"] += 1
        else: size_buckets["50+"] += 1

    source_diversity = Counter()
    for f in cluster_facts:
        sc = f["source_count"]
        if sc == 1: source_diversity["1 source"] += 1
        elif sc <= 3: source_diversity["2-3 sources"] += 1
        else: source_diversity["4+ sources"] += 1

    momentum_dist = Counter(f["momentum"] for f in cluster_facts)

    summary = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "sample_size": len(article_ids),
        "duration_seconds": round(duration, 1),
        "assigned": assigned,
        "spawned": spawned,
        "skipped": skipped,
        "errors": errors,
        "llm_calls": llm_used,
        "llm_skip_pct": round(100.0 * (assigned + spawned - llm_used) / max(1, assigned + spawned), 1),
        "total_threads_touched": len(set(thread_ids)),
        "size_distribution": dict(size_buckets),
        "source_diversity": dict(source_diversity),
        "momentum": dict(momentum_dist),
    }
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (OUT_DIR / "assignments.json").write_text(json.dumps(assignments, indent=2), encoding="utf-8")
    (OUT_DIR / "cluster_facts.json").write_text(json.dumps(cluster_facts, indent=2, default=str), encoding="utf-8")
    (OUT_DIR / "articles_per_thread.json").write_text(json.dumps(per_thread_articles, indent=2), encoding="utf-8")
    logger.info("Wrote validation artifacts to %s", OUT_DIR)
    logger.info("SUMMARY: %s", json.dumps(summary, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
