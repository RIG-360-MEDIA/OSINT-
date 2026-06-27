#!/usr/bin/env python3
"""worldwide_gen_live.py — §3 LIVE content-gen wiring (work order 2026-06-15).

Wraps the VALIDATED gen_hybrid (scripts/_worldwide_gen_sample.run_story) with the durable layer,
leaving that proven generator untouched:
  - topic + tags          -> folds §2 into the gen step (one cheap classification call)
  - fact_version stamp     -> sha256 of the fact-ledger; REGENERATE only on MATERIAL change
  - single-source          -> sources-only STUB (no synth article)
  - per-claim provenance   -> the verifier's per-unit faithfulness trace (persisted for citations)
  - write-through cache     -> analytics.story_generated_v8 (UPSERT)

HOSTED-FIRST: Guard-C/verify/topic are json_mode calls; the local Ollama node HANGS on json_mode
(120s timeout) so we force LOCAL_LLM_PRIMARY=0 for this path before importing the pool.

Usage:
  python worldwide_gen_live.py <story_id> [<story_id> ...]      # explicit set (Tier-1 full article)
  python worldwide_gen_live.py --surfaced N                     # top-N surfaced stories by article_count
  python worldwide_gen_live.py --aligned 500                    # A∪B = the FRONT-PAGE surfaced set (CRON uses this)
"""
import os
# MUST precede any backend import: json_mode hangs on the local node -> hosted-first.
os.environ["LOCAL_LLM_PRIMARY"] = "0"

import asyncio
import hashlib
import json
import sys
import time
import importlib.util
import re

sys.path.insert(0, "/app")

# Failure-signal phrases: if a generated headline/deck/body contains any of these, the model is telling
# us the ledger was empty -> treat as a GEN FAILURE (HELD), never a finished PUBLISHABLE article.
_NOFACTS_RE = re.compile(
    r"no facts|no verifiable|no corroborated|source ledger|no structured|fact-ledger contains no|"
    r"contains no entries|no entries|insufficient (facts|information|details)|no (specific )?details",
    re.IGNORECASE)

_spec = importlib.util.spec_from_file_location("ww", "/app/scripts/_worldwide_gen_sample.py")
ww = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ww)

from sqlalchemy import text  # noqa: E402
from backend.database import get_db  # noqa: E402

# Canonical topic enum (LOCKED by analytics 2026-06-16). Front-page sections draw from this set.
CANON_TOPICS = (
    "POLITICS", "GOVERNANCE", "SECURITY", "INTERNATIONAL", "BUSINESS", "FINANCE",
    "TECHNOLOGY", "SCIENCE", "ENVIRONMENT", "HEALTH", "SPORTS", "SOCIETY", "CULTURE",
    "LEGAL", "INFRASTRUCTURE", "AGRICULTURE", "OTHER",
)
# Map legacy / near-miss labels into the canonical set.
_TOPIC_ALIAS = {
    "SOCIAL": "SOCIETY", "ECONOMY": "FINANCE", "TECH": "TECHNOLOGY",
    "WORLD": "INTERNATIONAL", "ENV": "ENVIRONMENT", "BUSINESS/FINANCE": "BUSINESS",
    "INFRA": "INFRASTRUCTURE", "AGRI": "AGRICULTURE",
}
TOPIC_SYS = (
    "Classify this news story from its fact-ledger. Return STRICT JSON: "
    '{"topic":"<ONE of: ' + ", ".join(CANON_TOPICS) + '>",'
    '"tags":["3-6 short lowercase topical tags"]}'
)


def fact_version(ledger_text: str) -> str:
    return hashlib.sha256(ledger_text.encode("utf-8")).hexdigest()[:16]


async def classify_topic(ledger_text: str) -> dict:
    try:
        raw = await ww._llm(TOPIC_SYS, ledger_text[:6000], model=ww.GEN_MODEL,
                            json_mode=True, max_tokens=250)
        d = ww._parse_json(raw)
        topic = (d.get("topic") or "OTHER").strip().upper()
        topic = _TOPIC_ALIAS.get(topic, topic)
        if topic not in CANON_TOPICS:           # lock: anything off-enum -> OTHER
            topic = "OTHER"
        tags = [str(t).strip().lower() for t in (d.get("tags") or []) if str(t).strip()][:6]
        return {"topic": topic, "tags": tags}
    except Exception as exc:  # noqa: BLE001
        print(f"    topic-classify failed: {str(exc)[:80]}", flush=True)
        return {"topic": "OTHER", "tags": []}


# member_hash = md5 of the ORDERED member-article set; computed in-SQL so every write stamps the CURRENT
# membership (regen then fires on re-clustering, not just fact_version change — Task 1 2026-06-19).
_MH_SQL = ("(SELECT md5(coalesce(string_agg(article_id::text, ',' ORDER BY article_id),'')) "
           "FROM analytics.story_cluster_members_v8 WHERE story_id = :sid)")
_UPSERT = text(f"""
    INSERT INTO analytics.story_generated_v8
      (story_id, headline, deck, body, topic, tags, strategy, status, tier,
       guard_c, verify, claim_provenance, fact_version, member_hash, word_count, run_id, updated_at)
    VALUES (:sid,:h,:d,:b,:topic,:tags,:strat,:status,:tier,
       CAST(:gc AS jsonb), CAST(:vf AS jsonb), CAST(:cp AS jsonb), :fv, {_MH_SQL}, :wc,:rid, now())
    ON CONFLICT (story_id) DO UPDATE SET
      headline=EXCLUDED.headline, deck=EXCLUDED.deck, body=EXCLUDED.body,
      topic=EXCLUDED.topic, tags=EXCLUDED.tags, strategy=EXCLUDED.strategy,
      status=EXCLUDED.status, tier=EXCLUDED.tier, guard_c=EXCLUDED.guard_c,
      verify=EXCLUDED.verify, claim_provenance=EXCLUDED.claim_provenance,
      fact_version=EXCLUDED.fact_version, member_hash=EXCLUDED.member_hash,
      word_count=EXCLUDED.word_count, run_id=EXCLUDED.run_id, updated_at=now()
""")


async def process(db, sid: str, run_id: int) -> tuple[str, str]:
    L = await ww.load_ledger(db, sid)
    cl = L.get("cluster") or {}
    ltext = ww.ledger_to_text(L)
    fv = fact_version(ltext)

    # material-change guard: skip regen ONLY if BOTH fact-version AND member-set are unchanged.
    # (Re-clustering re-carves memberships without necessarily bumping facts -> must also check member_hash.)
    cur_mh = (await db.execute(
        text("SELECT md5(coalesce(string_agg(article_id::text, ',' ORDER BY article_id),'')) "
             "FROM analytics.story_cluster_members_v8 WHERE story_id=:s"), {"s": sid})).scalar()
    row = (await db.execute(
        text("SELECT fact_version, member_hash FROM analytics.story_generated_v8 WHERE story_id=:s"),
        {"s": sid})).first()
    if os.environ.get("FORCE_REGEN") != "1" and row and row[0] == fv and row[1] == cur_mh:
        return ("SKIP-unchanged", sid)

    topic = await classify_topic(ltext)

    # single-source -> sources-only stub (no synth article)
    indep = cl.get("independent_source_count") or 0
    if indep <= 1:
        rec = dict(sid=sid, h=cl.get("representative_title"), d=None, b=None,
                   topic=topic["topic"], tags=topic["tags"], strat="stub", status="STUB",
                   tier=0, gc=None, vf=None, cp=None, fv=fv, wc=0, rid=run_id)
        await db.execute(_UPSERT, rec)
        await db.commit()
        return ("STUB", sid)

    # HARD PRECONDITION (2026-06-17): an EMPTY fact-ledger is NOT publishable. The faithfulness verifier
    # PASSES "no facts available" articles (they're faithful to an empty input — the gate had no
    # precondition), so 973/1097 PUBLISHABLE rows were factless. Refuse to generate at all -> HELD-stub.
    if not (L.get("facts") or []):
        rec = dict(sid=sid, h=cl.get("representative_title"), d=None, b=None,
                   topic=topic["topic"], tags=topic["tags"], strat="stub",
                   status="HELD (no facts: empty ledger)", tier=0,
                   gc=None, vf=None, cp=None, fv=fv, wc=0, rid=run_id)
        await db.execute(_UPSERT, rec)
        await db.commit()
        return ("HELD-no-facts", sid)

    r = await ww.run_story(L)
    ch = r.get("chosen") or {}
    held = "HELD" in (r.get("status") or "")
    # GO decision (analytics 2026-06-16): surface a full article ONLY for clean PUBLISHABLE
    # (Guard-C ONE + verify pass). HELD (multi-event giant) or extractive -> sources-only stub,
    # never a single synth article that would misrepresent a multi-event cluster.
    if held or not ch:
        rec = dict(sid=sid, h=cl.get("representative_title"), d=None, b=None,
                   topic=topic["topic"], tags=topic["tags"], strat="stub",
                   status=r.get("status"), tier=0,
                   gc=json.dumps(r.get("guard_c")) if r.get("guard_c") is not None else None,
                   vf=None, cp=None, fv=fv, wc=0, rid=run_id)
        await db.execute(_UPSERT, rec)
        await db.commit()
        return (r.get("status"), sid)
    # Fix #2 (2026-06-17): NEVER ship "no facts available" as headline/deck/body. If it slips through
    # (facts present but the model still emitted a failure phrase), treat it as a FAILURE -> HELD-stub.
    _emitted = " ".join(str(x or "") for x in (ch.get("headline"), ch.get("deck"), ch.get("body")))
    if _NOFACTS_RE.search(_emitted):
        rec = dict(sid=sid, h=cl.get("representative_title"), d=None, b=None,
                   topic=topic["topic"], tags=topic["tags"], strat="stub",
                   status="HELD (no-facts output rejected)", tier=0,
                   gc=json.dumps(r.get("guard_c")) if r.get("guard_c") is not None else None,
                   vf=None, cp=None, fv=fv, wc=0, rid=run_id)
        await db.execute(_UPSERT, rec)
        await db.commit()
        return ("HELD-nofacts-output", sid)
    verify = ch.get("verify") if isinstance(ch.get("verify"), dict) else None
    provenance = (verify or {}).get("units")
    rec = dict(
        sid=sid,
        h=ch.get("headline") or cl.get("representative_title"),
        d=ch.get("deck"),
        b=ch.get("body"),
        topic=topic["topic"], tags=topic["tags"],
        strat=ch.get("strategy") or "extractive",
        status=r.get("status"),
        tier=1 if ch else 0,
        gc=json.dumps(r.get("guard_c")) if r.get("guard_c") is not None else None,
        vf=json.dumps(verify) if verify is not None else None,
        cp=json.dumps(provenance) if provenance is not None else None,
        fv=fv, wc=ch.get("words") or 0, rid=run_id,
    )
    await db.execute(_UPSERT, rec)
    await db.commit()
    return (r.get("status"), sid)


async def _surfaced_ids(db, n: int) -> list[str]:
    rows = (await db.execute(text(f"""
        SELECT story_id::text FROM analytics.story_clusters_v8
        WHERE NOT is_template_family
          AND (independent_source_count >= 3 OR rescued_from_story_id IS NOT NULL)
          AND EXISTS (SELECT 1 FROM analytics.story_facts_v8 f WHERE f.story_id = story_clusters_v8.story_id)
        ORDER BY article_count DESC NULLS LAST
        LIMIT {int(n)}
    """))).all()
    return [r[0] for r in rows]


async def _ranked_ids(db, n: int) -> list[str]:
    """Top-N SURFACED stories by importance_score = the cards' shown set. Gen these -> long-reads.
    No facts-exist filter (the shown set is ranked by importance; gen handles thin/single-source -> stub)."""
    rows = (await db.execute(text(f"""
        SELECT story_id::text FROM analytics.story_clusters_v8
        WHERE NOT is_template_family
          AND (independent_source_count >= 3 OR rescued_from_story_id IS NOT NULL)
        ORDER BY importance_score DESC NULLS LAST
        LIMIT {int(n)}
    """))).all()
    return [r[0] for r in rows]


async def _aligned_ids(db, n_a: int = 500) -> list[str]:
    """A ∪ B = exactly the set the FRONT PAGE surfaces (gen-alignment contract 2026-06-16).

    A = top-n_a by the FRONT-PAGE importance (recency-GATE + pile-DEMOTION), ported VERBATIM from the
        Next-app ranking over the surfaced/non-junk pool — NOT the engine's raw importance_score, which
        the page does not use. This naturally floats recent+coherent stories and sinks old/multi-event piles.
    B = night-repair-v8 split children (the "Full coverage" hub members) seen within ~4 days — each needs
        its own article or the hubs are half-empty.
    De-duped, A first (importance order) so the top cards fill first."""
    rows_a = (await db.execute(text("""
        WITH maxd AS (SELECT max(last_seen_at) m FROM analytics.story_clusters_v8),
        ranked AS (
          SELECT sc.story_id::text AS sid,
            round((
                ( 1.0*ln(1+sc.independent_source_count)
                + 0.5*ln(1+least(coalesce(f.fc,0),15))
                + (CASE coalesce(a.source_tier,2) WHEN 1 THEN 1.0 WHEN 2 THEN 0.3 ELSE 0.0 END) )
              * (0.15 + 0.85*exp(-extract(epoch FROM (maxd.m - sc.last_seen_at))/86400.0/1.5))
              * (CASE WHEN g.strategy='stub' AND g.status ILIKE '%HELD%' THEN 0.25 ELSE 1.0 END)
            )::numeric, 2) AS importance
          FROM analytics.story_clusters_v8 sc
          CROSS JOIN maxd
          LEFT JOIN LATERAL (SELECT count(*) AS fc FROM analytics.story_facts_v8 f
                             WHERE f.story_id = sc.story_id) f ON true
          LEFT JOIN articles a ON a.id = sc.representative_article_id
          LEFT JOIN analytics.story_generated_v8 g ON g.story_id = sc.story_id
          WHERE sc.suppression_reason IS NULL
            -- PHANTOM GUARD (2026-06-17): never select a cluster with ZERO member rows. The forward loop
            -- (story_loader ALGO_VERSION=pf-v1/tg-v3, mismatched to the v4/_v8 keeper) manufactured ~147k
            -- member-less "phantom" clusters with inflated counts -> factless gen + front-page pollution.
            AND EXISTS(SELECT 1 FROM analytics.story_cluster_members_v8 mm WHERE mm.story_id = sc.story_id)
            AND sc.independent_source_count IS NOT NULL
            AND sc.representative_title !~* '(share price|top picks|result 20[0-9]{2}|gainers (and|&) losers|dream ?11|sensex|nifty|share market)'
        )
        SELECT sid FROM ranked ORDER BY importance DESC NULLS LAST LIMIT :lim
    """), {"lim": int(n_a)})).all()
    rows_b = (await db.execute(text("""
        SELECT story_id::text FROM analytics.story_clusters_v8
        WHERE algo_version='night-repair-v8' AND last_seen_at > now()-interval '4 days'
    """))).all()
    # B FIRST: the hub members ("Full coverage") are the biggest coverage gap (≈1% vs the top A
    # cards which are already mostly filled), and a half-empty hub is the most visible breakage —
    # so fill those first, then the A mid-tier. skip-unchanged makes the already-done ones cheap
    # regardless of order, so this only changes WHICH gaps close first, not the converged set.
    seen: set = set()
    out: list[str] = []
    for r in list(rows_b) + list(rows_a):
        if r[0] not in seen:
            seen.add(r[0])
            out.append(r[0])
    return out


async def main() -> int:
    run_id = int(os.environ.get("RUN_ID") or time.time())
    args = sys.argv[1:]
    async with get_db() as db:
        if args and args[0] == "--surfaced":
            ids = await _surfaced_ids(db, int(args[1]) if len(args) > 1 else 50)
        elif args and args[0] == "--ranked":
            ids = await _ranked_ids(db, int(args[1]) if len(args) > 1 else 300)
        elif args and args[0] == "--aligned":
            # A ∪ B = the front-page surfaced set (gen-alignment contract). Generate exactly what
            # the page shows so cards open to real reads instead of stubs.
            ids = await _aligned_ids(db, int(args[1]) if len(args) > 1 else 500)
        elif args and args[0] == "--backlog":
            # ALL ledgered+surfaceable stories, sharded by env SHARD/NSHARD for parallel fill.
            # skip-unchanged guard makes already-done (same fact_version) ones cheap.
            ids = await _surfaced_ids(db, 10**9)
            _sh = int(os.environ.get('SHARD', '-1')); _ns = int(os.environ.get('NSHARD', '1'))
            if _sh >= 0:
                ids = ids[_sh::_ns]
        else:
            ids = args
        print(f"gen-live: {len(ids)} stories  run_id={run_id}", flush=True)
        counts: dict[str, int] = {}
        for sid in ids:
            try:
                status, _ = await process(db, sid, run_id)
            except Exception as exc:  # noqa: BLE001
                status = f"ERROR: {str(exc)[:100]}"
            key = status.split(" |")[0].split(":")[0].strip()
            counts[key] = counts.get(key, 0) + 1
            print(f"  {sid[:8]}  {status}", flush=True)
    print(f"\n===== gen-live tallies ({run_id}) =====", flush=True)
    for k, v in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"  {v:>4}  {k}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
