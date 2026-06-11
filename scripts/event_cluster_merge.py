"""Story-chain merge pass over event_clusters.

Finds pairs of clusters that describe the same real-world incident but got
split (different canonical_date / event_type / actor surface form), then asks
the LLM judge whether to merge.

Merge candidates pass these structural gates first:
  - canonical_actors Jaccard overlap >= 0.5
  - |canonical_date diff| <= 30 days
  - description SequenceMatcher ratio >= 0.4

Then the LLM judge gives a final SAME/DIFFERENT vote. On SAME:
  - Repoint article_events.event_cluster_id from the SMALLER cluster to the LARGER
  - Merge canonical_actors as union
  - Recompute article_count + source_count
  - Mark the smaller cluster is_active=FALSE

Output: /tmp/event_merge_v2/summary.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402

from backend.database import get_db  # noqa: E402
from backend.nlp.groq_client import (  # noqa: E402
    GroqCallFailed,
    GroqQuotaExhausted,
    call_groq,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("merge")

OUT_DIR = Path("/tmp/event_merge_v2")
OUT_DIR.mkdir(exist_ok=True)

ACTOR_JACCARD_FLOOR = 0.5
DATE_DIFF_DAYS = 30
DESC_RATIO_FLOOR = 0.4


def actor_jaccard(a, b):
    sa = {s.strip().lower() for s in (a or []) if s}
    sb = {s.strip().lower() for s in (b or []) if s}
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def desc_ratio(a, b):
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a.lower()[:200], b.lower()[:200]).ratio()


_JUDGE_SYSTEM = (
    "You are merging news event clusters. Two clusters describe the SAME "
    "real-world story only if they refer to the same specific incident, "
    "even when their canonical date or event_type differs (the same incident "
    "is often reported across multiple days with evolving angles). Be strict: "
    "two unrelated events sharing an actor are DIFFERENT."
)

_JUDGE_USER = """Cluster A
  Date: {da}  Type: {ta}
  Actors: {aa}
  Canonical: {desca}

Cluster B
  Date: {db}  Type: {tb}
  Actors: {ab}
  Canonical: {descb}

Are these the SAME real-world story (possibly different angles/days)? Output STRICT JSON:
{{"verdict": "SAME" | "DIFFERENT", "confidence": 0.0-1.0, "reason": "<one short sentence>"}}"""


async def llm_judge_merge(a, b):
    user = _JUDGE_USER.format(
        da=a["canonical_date"], ta=a["canonical_event_type"] or "?",
        aa=", ".join(a["canonical_actors"] or [])[:200],
        desca=(a["canonical_description"] or "")[:280],
        db=b["canonical_date"], tb=b["canonical_event_type"] or "?",
        ab=", ".join(b["canonical_actors"] or [])[:200],
        descb=(b["canonical_description"] or "")[:280],
    )
    try:
        raw = await call_groq(
            system=_JUDGE_SYSTEM, user=user,
            task_type="classification", json_response=True,
            max_tokens_override=200,
        )
        parsed = json.loads(raw)
        v = (parsed.get("verdict") or "").upper()
        return {
            "verdict": "SAME" if v == "SAME" else "DIFFERENT",
            "confidence": float(parsed.get("confidence") or 0.5),
            "reason": str(parsed.get("reason") or "")[:200],
        }
    except (GroqCallFailed, GroqQuotaExhausted, json.JSONDecodeError, ValueError, KeyError) as e:
        return {"verdict": "DIFFERENT", "confidence": 0.0, "reason": f"err: {str(e)[:100]}"}


async def fetch_candidate_pairs(db, limit_pairs):
    """Return pairs of clusters that pass the structural gates."""
    rows = await db.execute(text("""
        SELECT a.id::text AS a_id, b.id::text AS b_id,
               a.canonical_description AS a_desc, b.canonical_description AS b_desc,
               a.canonical_actors AS a_actors, b.canonical_actors AS b_actors,
               a.canonical_event_type AS a_etype, b.canonical_event_type AS b_etype,
               a.canonical_date AS a_date, b.canonical_date AS b_date,
               a.article_count AS a_size, b.article_count AS b_size
          FROM event_clusters a
          JOIN event_clusters b ON a.id < b.id
         WHERE a.is_active AND b.is_active
           AND a.canonical_actors && b.canonical_actors
           AND ABS(a.canonical_date - b.canonical_date) <= :ddays
           AND (a.article_count > 1 OR b.article_count > 1)
         LIMIT :n
    """), {"ddays": DATE_DIFF_DAYS, "n": limit_pairs})
    return [dict(r._mapping) for r in rows.fetchall()]


async def merge_clusters(db, keep_id, drop_id):
    """Move articles from drop_id into keep_id, deactivate drop, recompute keep aggregates."""
    drop_row = (await db.execute(
        text("SELECT canonical_actors FROM event_clusters WHERE id = CAST(:c AS uuid)"),
        {"c": drop_id},
    )).fetchone()
    keep_row = (await db.execute(
        text("SELECT canonical_actors FROM event_clusters WHERE id = CAST(:c AS uuid)"),
        {"c": keep_id},
    )).fetchone()
    merged_actors = sorted(set(keep_row.canonical_actors or []) | set(drop_row.canonical_actors or []))

    await db.execute(
        text("UPDATE article_events SET event_cluster_id = CAST(:k AS uuid) WHERE event_cluster_id = CAST(:d AS uuid)"),
        {"k": keep_id, "d": drop_id},
    )
    await db.execute(
        text("UPDATE event_clusters SET is_active = FALSE WHERE id = CAST(:d AS uuid)"),
        {"d": drop_id},
    )
    await db.execute(text("""
        UPDATE event_clusters
           SET canonical_actors = :actors,
               article_count = (
                 SELECT COUNT(DISTINCT ae.article_id) FROM article_events ae
                  WHERE ae.event_cluster_id = CAST(:k AS uuid)
               ),
               source_count = (
                 SELECT COUNT(DISTINCT a.source_id) FROM article_events ae
                   JOIN articles a ON a.id = ae.article_id
                  WHERE ae.event_cluster_id = CAST(:k AS uuid)
               ),
               last_updated_at = NOW()
         WHERE id = CAST(:k AS uuid)
    """), {"actors": merged_actors, "k": keep_id})


async def run(args):
    async with get_db() as db:
        pairs = await fetch_candidate_pairs(db, args.max_pairs)
    logger.info("Found %d candidate pairs after structural gate", len(pairs))

    # Apply Jaccard + desc ratio refinement
    refined = []
    for p in pairs:
        aj = actor_jaccard(p["a_actors"], p["b_actors"])
        dr = desc_ratio(p["a_desc"], p["b_desc"])
        if aj >= ACTOR_JACCARD_FLOOR and dr >= DESC_RATIO_FLOOR:
            refined.append({**p, "actor_jaccard": aj, "desc_ratio": dr})
    logger.info("Refined to %d pairs (Jaccard>=%.2f, desc>=%.2f)",
                len(refined), ACTOR_JACCARD_FLOOR, DESC_RATIO_FLOOR)

    counts = {"considered": 0, "merged": 0, "llm_same": 0, "llm_diff": 0, "errors": 0}
    merged_log = []
    t0 = time.time()
    last_report = t0
    deactivated_ids: set[str] = set()

    for i, p in enumerate(refined):
        if p["a_id"] in deactivated_ids or p["b_id"] in deactivated_ids:
            continue
        counts["considered"] += 1
        verdict = await llm_judge_merge(
            {"canonical_date": p["a_date"], "canonical_event_type": p["a_etype"],
             "canonical_actors": p["a_actors"], "canonical_description": p["a_desc"]},
            {"canonical_date": p["b_date"], "canonical_event_type": p["b_etype"],
             "canonical_actors": p["b_actors"], "canonical_description": p["b_desc"]},
        )
        if verdict["verdict"] == "SAME":
            counts["llm_same"] += 1
            keep_id = p["a_id"] if (p["a_size"] or 0) >= (p["b_size"] or 0) else p["b_id"]
            drop_id = p["b_id"] if keep_id == p["a_id"] else p["a_id"]
            try:
                async with get_db() as db2:
                    await merge_clusters(db2, keep_id, drop_id)
                    await db2.commit()
                counts["merged"] += 1
                deactivated_ids.add(drop_id)
                merged_log.append({
                    "keep_id": keep_id, "drop_id": drop_id,
                    "a_desc": p["a_desc"][:120], "b_desc": p["b_desc"][:120],
                    "actor_jaccard": p["actor_jaccard"], "desc_ratio": p["desc_ratio"],
                    "llm_conf": verdict["confidence"], "reason": verdict["reason"],
                })
            except Exception as e:  # pragma: no cover
                logger.exception("merge failed %s -> %s", drop_id, keep_id)
                counts["errors"] += 1
        else:
            counts["llm_diff"] += 1

        now = time.time()
        if now - last_report >= 10 or (i + 1) == len(refined):
            rate = (i + 1) / max(now - t0, 1)
            logger.info("PROGRESS %d/%d · %.1f pairs/sec · %s", i + 1, len(refined), rate, counts)
            last_report = now

    # Final counts
    async with get_db() as db:
        before_after = await db.execute(text("""
            SELECT
              COUNT(*) FILTER (WHERE is_active) AS active_clusters,
              COUNT(*) FILTER (WHERE is_active AND article_count > 1) AS multi_article,
              COUNT(*) FILTER (WHERE NOT is_active) AS deactivated
              FROM event_clusters
        """))
        snap = dict(before_after.fetchone()._mapping)

    summary = {
        "duration_sec": round(time.time() - t0, 1),
        "counts": counts,
        "post_merge_snapshot": snap,
    }
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    (OUT_DIR / "merged_log.json").write_text(json.dumps(merged_log, indent=2, default=str), encoding="utf-8")
    logger.info("DONE · %s", json.dumps(summary, indent=2, default=str))
    return 0


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--max-pairs", type=int, default=5000,
                   help="cap initial candidate pairs (structural gate)")
    args = p.parse_args()
    sys.exit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
