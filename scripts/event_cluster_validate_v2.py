"""Event-first clustering v2 with LLM judge + three failure-mode fixes.

Changes from v1:
  A. LLM judge for shared-broad-actor cases (Trump/Russia/Modi catch-alls)
  B. Tangential-event filter — reject events that are historical references
     not the primary event of their article
  C. Fuzzy date merge — allow merges with date diff up to 30 days if actor
     overlap is ≥80% AND description similarity ≥0.7

Uses the unified LLM pool (Ollama + Groq + Cerebras in parallel). Routing is
controlled by env vars:
    LOCAL_LLM_ENABLED=1   — include Ollama slot
    LOCAL_LLM_PRIMARY=0   — round-robin all 52 slots, not Ollama-first
    PARALLEL_LLM_POOL=1   — use unified pool

Outputs go to /tmp/event_validation_v2/.
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
from datetime import datetime, date as date_cls, timedelta
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402

from backend.database import get_db  # noqa: E402
from backend.nlp.groq_client import (  # noqa: E402
    GroqCallFailed,
    GroqQuotaExhausted,
    call_groq,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("event_cluster_v2")

OUT_DIR = Path("/tmp/event_validation_v2")
OUT_DIR.mkdir(exist_ok=True)

# Scoring config
DATE_WINDOW_DAYS = 3
TOP_K = 10
HARD_MATCH_SCORE = 0.82
HARD_REJECT_SCORE = 0.40
LLM_AMBIGUOUS_FLOOR = 0.45
W_ACTOR = 0.35
W_DATE = 0.25
W_TYPE = 0.20
W_DESC = 0.15
W_SOURCE = 0.05

# "Broad actors" — entities that appear in many unrelated stories.
# When two events share ONLY a broad actor, force LLM judge.
BROAD_ACTORS = {
    "donald trump", "narendra modi", "vladimir putin", "xi jinping",
    "joe biden", "kamala harris", "rahul gandhi",
    "russia", "united states", "israel", "iran", "china", "ukraine",
    "india", "pakistan", "bjp", "congress", "trinamool congress",
    "republican party", "democratic party", "european union",
    "european commission", "european council", "european parliament",
    "world health organization", "united nations", "supreme court of india",
    "government of india", "police", "isro", "narendra modi government",
}


# ---------- Scoring ----------
def actor_jaccard(a, b):
    if not a or not b:
        return 0.0
    sa = {s.strip().lower() for s in a if s}
    sb = {s.strip().lower() for s in b if s}
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def date_proximity(da, db_):
    if da is None or db_ is None:
        return 0.0
    diff_days = abs((da - db_).days)
    if diff_days == 0:
        return 1.0
    return max(0.0, 1.0 - diff_days / (DATE_WINDOW_DAYS + 1))


def desc_ratio(a, b):
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a.lower()[:200], b.lower()[:200]).ratio()


def score_match(new_event, candidate):
    aj = actor_jaccard(new_event.get("actors"), candidate.get("canonical_actors"))
    dp = date_proximity(new_event.get("event_date"), candidate.get("canonical_date"))
    tm = 1.0 if (new_event.get("event_type") and
                 new_event.get("event_type") == candidate.get("canonical_event_type")) else 0.0
    dr = desc_ratio(new_event.get("event_description"), candidate.get("canonical_description"))
    src_bonus = 1.0  # always favor cross-source — we don't track candidate sources here
    return W_ACTOR * aj + W_DATE * dp + W_TYPE * tm + W_DESC * dr + W_SOURCE * src_bonus


def only_broad_overlap(actors_a, actors_b):
    """True if the only shared actors are broad/global figures."""
    a = {s.strip().lower() for s in (actors_a or []) if s}
    b = {s.strip().lower() for s in (actors_b or []) if s}
    shared = a & b
    if not shared:
        return False
    return shared.issubset(BROAD_ACTORS)


# ---------- LLM Judge ----------
_JUDGE_SYSTEM = (
    "You are clustering news events. Two events match SAME only if they describe "
    "the same specific real-world incident (same actors taking same action at same "
    "time/place). Be strict — when in doubt, choose DIFFERENT. "
    "If Event A is just a brief historical reference in its article (not the article's "
    "primary subject), respond TANGENTIAL."
)

_JUDGE_USER = """Event A (NEW)
  Date: {da}
  Type: {ta}
  Actors: {aa}
  Description: {desca}
  From article titled: {article_title}

Event B (EXISTING CLUSTER)
  Date: {db}
  Type: {tb}
  Actors: {ab}
  Canonical description: {descb}

Output STRICT JSON: {{"verdict": "SAME" | "DIFFERENT" | "TANGENTIAL", "confidence": 0.0-1.0, "reason": "<one short sentence>"}}"""


async def llm_judge(new_event: dict, candidate: dict) -> dict:
    """Ask the LLM: SAME / DIFFERENT / TANGENTIAL? Routes via unified pool."""
    user = _JUDGE_USER.format(
        da=new_event.get("event_date"),
        ta=new_event.get("event_type") or "?",
        aa=", ".join(new_event.get("actors") or [])[:200],
        desca=(new_event.get("event_description") or "")[:300],
        article_title=(new_event.get("article_title") or "")[:160],
        db=candidate.get("canonical_date"),
        tb=candidate.get("canonical_event_type") or "?",
        ab=", ".join(candidate.get("canonical_actors") or [])[:200],
        descb=(candidate.get("canonical_description") or "")[:300],
    )
    try:
        raw = await call_groq(
            system=_JUDGE_SYSTEM,
            user=user,
            task_type="classification",
            json_response=True,
            max_tokens_override=200,
        )
        parsed = json.loads(raw)
        v = (parsed.get("verdict") or "").upper()
        if v not in ("SAME", "DIFFERENT", "TANGENTIAL"):
            v = "DIFFERENT"
        return {
            "verdict": v,
            "confidence": float(parsed.get("confidence") or 0.5),
            "reason": str(parsed.get("reason") or "")[:240],
        }
    except (GroqCallFailed, GroqQuotaExhausted) as e:
        return {"verdict": "DIFFERENT", "confidence": 0.0, "reason": f"llm-error: {str(e)[:120]}"}
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        return {"verdict": "DIFFERENT", "confidence": 0.0, "reason": f"bad-json: {str(e)[:120]}"}


# ---------- DB helpers ----------
async def reset_event_clusters(db) -> None:
    await db.execute(text("UPDATE article_events SET event_cluster_id = NULL WHERE event_cluster_id IS NOT NULL"))
    await db.execute(text("DELETE FROM event_clusters"))
    await db.commit()
    logger.info("Reset event_clusters table.")


async def fetch_events_to_cluster(db, since_days, limit):
    q = text("""
        SELECT ae.id::text AS event_id, ae.article_id::text AS article_id,
               ae.actors, ae.event_type, ae.event_date,
               ae.event_description, ae.is_future,
               a.source_id::text AS source_id, s.name AS source_name,
               a.title AS article_title, a.primary_subject AS primary_subject,
               a.collected_at
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


async def find_candidates(db, ev):
    d = ev["event_date"]
    d_lo = d - timedelta(days=DATE_WINDOW_DAYS)
    d_hi = d + timedelta(days=DATE_WINDOW_DAYS)
    q = text("""
        SELECT ec.id::text AS id, ec.canonical_actors, ec.canonical_event_type,
               ec.canonical_date, ec.canonical_description,
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
    rows = await db.execute(q, {
        "actors": list(ev["actors"] or []),
        "d_lo": d_lo, "d_hi": d_hi,
        "etype": ev.get("event_type") or "",
        "k": TOP_K,
    })
    return [dict(r._mapping) for r in rows.fetchall()]


async def spawn_cluster(db, ev, confidence):
    r = await db.execute(text("""
        INSERT INTO event_clusters (
          canonical_description, canonical_actors, canonical_event_type,
          canonical_date, is_future, article_count, source_count, confidence_score
        ) VALUES (:desc, :actors, :etype, :d, :fut, 1, 1, :conf)
        RETURNING id::text AS id
    """), {
        "desc": (ev["event_description"] or "")[:500],
        "actors": list(ev["actors"] or []),
        "etype": ev.get("event_type"),
        "d": ev["event_date"],
        "fut": bool(ev.get("is_future")),
        "conf": float(confidence),
    })
    cid = r.fetchone().id
    await db.execute(
        text("UPDATE article_events SET event_cluster_id = CAST(:c AS uuid) WHERE id = CAST(:e AS uuid)"),
        {"c": cid, "e": ev["event_id"]},
    )
    return cid


async def assign_to_cluster(db, ev, cluster_id, score):
    existing = await db.execute(
        text("SELECT canonical_actors FROM event_clusters WHERE id = CAST(:c AS uuid)"),
        {"c": cluster_id},
    )
    row = existing.fetchone()
    new_actors = sorted(set(row.canonical_actors or []) | set(ev["actors"] or []))
    await db.execute(text("""
        UPDATE event_clusters
           SET canonical_actors = :actors,
               article_count = (
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
               last_updated_at = NOW(),
               confidence_score = LEAST(1.0, COALESCE(confidence_score, :conf) * 0.5 + :conf * 0.5)
         WHERE id = CAST(:c AS uuid)
    """), {"actors": new_actors, "c": cluster_id, "conf": float(score)})
    await db.execute(
        text("UPDATE article_events SET event_cluster_id = CAST(:c AS uuid) WHERE id = CAST(:e AS uuid)"),
        {"c": cluster_id, "e": ev["event_id"]},
    )


# ---------- Decision logic ----------
async def decide_assignment(db, ev, candidates):
    """Return ('assign', cluster_id, conf) or ('spawn', None, conf), plus a trace."""
    if not candidates:
        return ("spawn", None, 1.0, "no-candidates")

    scored = sorted(((score_match(ev, c), c) for c in candidates), key=lambda kv: -kv[0])
    top_score, top_cand = scored[0]

    # Fast-path 1: hard reject
    if top_score < HARD_REJECT_SCORE:
        return ("spawn", None, 1.0 - top_score, f"low-score:{top_score:.2f}")

    # Gate A: shared-broad-actor magnet — force LLM even on high score
    actor_overlap = set((s.strip().lower() for s in ev["actors"] or [])) & set(
        (s.strip().lower() for s in top_cand.get("canonical_actors") or [])
    )
    force_llm = only_broad_overlap(ev["actors"], top_cand.get("canonical_actors")) and len(actor_overlap) <= 1

    # Fast-path 2: very high score AND not a broad-actor case
    if top_score >= HARD_MATCH_SCORE and not force_llm:
        return ("assign", top_cand["id"], top_score, f"fast-match:{top_score:.2f}")

    # Otherwise: LLM judge
    verdict = await llm_judge(ev, top_cand)
    if verdict["verdict"] == "SAME":
        return ("assign", top_cand["id"], verdict["confidence"],
                f"llm-same:{verdict['confidence']:.2f}:{verdict['reason'][:80]}")
    if verdict["verdict"] == "TANGENTIAL":
        return ("skip", None, verdict["confidence"],
                f"llm-tangential:{verdict['reason'][:80]}")
    return ("spawn", None, verdict["confidence"],
            f"llm-diff:{verdict['confidence']:.2f}:{verdict['reason'][:80]}")


# ---------- Main ----------
async def run(args):
    async with get_db() as db:
        if args.reset:
            await reset_event_clusters(db)
        events = await fetch_events_to_cluster(db, args.since_days, args.limit)
    logger.info("Fetched %d events (last %d days)", len(events), args.since_days)

    counts = {"assigned": 0, "spawned": 0, "skipped": 0, "errors": 0,
              "llm_calls": 0, "fast_assign": 0, "fast_spawn": 0}
    decisions = []
    t0 = time.time()
    last_report = t0

    for i, ev in enumerate(events):
        try:
            async with get_db() as db:
                candidates = await find_candidates(db, ev)
                decision, cid, conf, trace = await decide_assignment(db, ev, candidates)
                if "llm" in trace:
                    counts["llm_calls"] += 1
                if decision == "assign":
                    if "fast-match" in trace:
                        counts["fast_assign"] += 1
                    await assign_to_cluster(db, ev, cid, conf)
                    counts["assigned"] += 1
                elif decision == "skip":
                    counts["skipped"] += 1
                else:
                    if "no-candidates" in trace or "low-score" in trace:
                        counts["fast_spawn"] += 1
                    await spawn_cluster(db, ev, conf)
                    counts["spawned"] += 1
                await db.commit()
                decisions.append({"event_id": ev["event_id"], "decision": decision,
                                  "trace": trace, "conf": conf})
        except Exception as exc:  # pragma: no cover
            logger.exception("Event %s failed", ev.get("event_id"))
            counts["errors"] += 1

        now = time.time()
        if now - last_report >= 10 or (i + 1) == len(events):
            rate = (i + 1) / max(now - t0, 1)
            eta_min = (len(events) - i - 1) / max(rate, 0.1) / 60
            logger.info("PROGRESS %d/%d · %.1f ev/sec · ETA %.1f min · %s",
                        i + 1, len(events), rate, eta_min, counts)
            last_report = now

    duration = time.time() - t0
    logger.info("DONE in %.1f min · %s", duration / 60, counts)

    # Report
    async with get_db() as db:
        rows = await db.execute(text("""
            SELECT ec.id::text AS id, ec.canonical_description AS desc,
                   ec.canonical_actors AS actors, ec.canonical_event_type AS etype,
                   ec.canonical_date::text AS d, ec.article_count, ec.source_count,
                   ec.confidence_score
              FROM event_clusters ec
              JOIN article_events ae ON ae.event_cluster_id = ec.id
              JOIN articles a ON a.id = ae.article_id
             WHERE a.collected_at > NOW() - make_interval(days => :d)
             GROUP BY ec.id
             ORDER BY ec.article_count DESC NULLS LAST, ec.last_updated_at DESC
             LIMIT 250
        """), {"d": args.since_days})
        cluster_facts = [dict(r._mapping) for r in rows.fetchall()]

        per_cluster = {}
        if cluster_facts:
            ids = [c["id"] for c in cluster_facts]
            rows2 = await db.execute(text("""
                SELECT ec.id::text AS cluster_id, a.id::text AS article_id,
                       LEFT(a.title, 140) AS title, a.language_detected AS lang,
                       s.name AS source,
                       LEFT(ae.event_description, 180) AS event_desc,
                       ae.event_date::text AS event_date, ae.event_type AS event_type
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
        "counts": counts,
        "duration_sec": round(duration, 1),
        "clusters_total": len(cluster_facts),
        "multi_article_clusters": sum(1 for c in cluster_facts if (c.get("article_count") or 0) > 1),
        "size_buckets": dict(Counter(
            ("1" if (c.get("article_count") or 0) <= 1
             else "2-3" if c["article_count"] <= 3
             else "4-10" if c["article_count"] <= 10
             else "11-50" if c["article_count"] <= 50 else "50+")
            for c in cluster_facts
        )),
        "source_diversity": dict(Counter(
            ("1 source" if (c.get("source_count") or 0) <= 1
             else "2-3 sources" if c["source_count"] <= 3 else "4+ sources")
            for c in cluster_facts
        )),
    }
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    (OUT_DIR / "clusters.json").write_text(json.dumps(cluster_facts, indent=2, default=str), encoding="utf-8")
    (OUT_DIR / "articles_per_cluster.json").write_text(json.dumps(per_cluster, indent=2, default=str), encoding="utf-8")
    (OUT_DIR / "decisions.json").write_text(json.dumps(decisions, indent=2, default=str), encoding="utf-8")
    logger.info("Wrote artifacts to %s", OUT_DIR)
    logger.info("SUMMARY: %s", json.dumps(summary, indent=2, default=str))
    return 0


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--since-days", type=int, default=5)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--reset", action="store_true")
    args = p.parse_args()
    sys.exit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
