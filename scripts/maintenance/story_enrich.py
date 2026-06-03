#!/usr/bin/env python3
"""story_enrich.py — STEP 3 enrichment population (loader-enrichment-spec §3).

PHASE A (structural): story_timeline, story_sources, story_geo + the coverage half of
story_enrichment_status. Pure source-row aggregation (computed-not-generated): every value is a
SQL aggregate over story_cluster_members -> articles. Surfaced-only:
  NOT is_template_family AND (independent_source_count >= 3 OR rescued_from_story_id IS NOT NULL)
— so the 34K singletons and the suppressed blobs are skipped, and rescued sub-stories (even below
indep>=3) ARE enriched (a surfaced story must not appear naked).

PHASE B (extraction: facts/quotes/stance) is a separate run after the divergence design.

Fully recomputed per run (the 4 tables are derived) and run_id-stamped. Additive — touches no
core table. Read-mostly except the enrichment tables it owns.

Env: AB_DSN/DATABASE_URL_SYNC · PHASE (structural) · BREAKING_VELOCITY (10 = articles/hr in first 6h)
"""
from __future__ import annotations

import os
import re
import sys
import time
from collections import defaultdict

import psycopg2
from psycopg2.extras import execute_values

PHASE = os.environ.get("PHASE", "structural")
BREAKING_VELOCITY = float(os.environ.get("BREAKING_VELOCITY", "10"))
SURF = "(NOT is_template_family AND (independent_source_count >= 3 OR rescued_from_story_id IS NOT NULL))"

NUM_RE = re.compile(r"(\d[\d,]*(?:\.\d+)?)")
SCALE_RE = re.compile(r"\b(crore|lakhs?|million|billion|trillion|thousand|percent|per cent)\b", re.I)
CUR_RE = re.compile(r"[₹$€£]")


def extract_num_unit(object_text):
    """First number + a unit token (currency/scale/%) from a claim's object_text. Numbers compare
    only WITHIN a same-unit group, so no cross-unit scaling is needed."""
    if not object_text:
        return None, ""
    m = NUM_RE.search(object_text)
    if not m:
        return None, ""
    try:
        num = float(m.group(1).replace(",", ""))
    except ValueError:
        return None, ""
    unit = ""
    cur = CUR_RE.search(object_text)
    if cur:
        unit += cur.group(0)
    sc = SCALE_RE.search(object_text)
    if sc:
        unit += sc.group(1).lower()
    if unit == "" and num == int(num) and 1900 <= num <= 2099:
        return None, ""   # bare 4-digit year -> a date, not a quantity fact (under-include, safe)
    if "%" in object_text:
        unit += "%"
    return num, unit


def norm_measure(subject_text):
    """Normalized 'what is measured' = the claim subject. Conservative grouping key: subject
    variants collapse only when they really match; when in doubt they differ -> under-merge (safe)."""
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", (subject_text or "").lower()).split())[:60]


def structural(cur, run_id: int) -> None:
    surf_cte = f"surf AS (SELECT story_id FROM analytics.story_clusters WHERE {SURF})"

    # --- story_timeline: first/last/peak/velocity/span/is_breaking from member collected_at ---
    cur.execute("TRUNCATE analytics.story_timeline")
    cur.execute(f"""
        WITH {surf_cte},
        mem AS (SELECT m.story_id, a.collected_at FROM analytics.story_cluster_members m
                JOIN articles a ON a.id = m.article_id
                WHERE m.story_id IN (SELECT story_id FROM surf) AND a.collected_at IS NOT NULL),
        fs AS (SELECT story_id, min(collected_at) first_seen, max(collected_at) last_seen, count(*) n FROM mem GROUP BY 1),
        v6 AS (SELECT m.story_id, count(*) first6h FROM mem m JOIN fs ON fs.story_id = m.story_id
               WHERE m.collected_at <= fs.first_seen + interval '6 hours' GROUP BY 1),
        pk AS (SELECT story_id, date_trunc('hour', collected_at) hr, count(*) c,
                      row_number() OVER (PARTITION BY story_id ORDER BY count(*) DESC, date_trunc('hour', collected_at)) rn
               FROM mem GROUP BY 1, 2)
        INSERT INTO analytics.story_timeline
          (story_id, first_seen_at, last_seen_at, peak_at, peak_articles_per_hour, velocity, span_hours, is_breaking, run_id)
        SELECT fs.story_id, fs.first_seen, fs.last_seen,
               pk1.hr, pk1.c,
               round(coalesce(v6.first6h, 0) / 6.0, 2),
               round(extract(epoch FROM fs.last_seen - fs.first_seen) / 3600.0, 1),
               (coalesce(v6.first6h, 0) / 6.0) >= %s,
               %s
        FROM fs
        LEFT JOIN v6 ON v6.story_id = fs.story_id
        LEFT JOIN pk pk1 ON pk1.story_id = fs.story_id AND pk1.rn = 1
    """, (BREAKING_VELOCITY, run_id))
    n_tl = cur.rowcount

    # --- story_sources: per-source counts + pickup latency + canonical origin ---
    cur.execute("TRUNCATE analytics.story_sources")
    cur.execute(f"""
        WITH {surf_cte}
        INSERT INTO analytics.story_sources
          (story_id, source_id, articles_from_source, first_seen_at, source_country, is_canonical_origin, run_id)
        SELECT m.story_id, m.source_id, count(*), min(a.collected_at),
               (array_agg(rtrim(a.source_country) ORDER BY a.collected_at) FILTER (WHERE a.source_country IS NOT NULL))[1],
               false, %s
        FROM analytics.story_cluster_members m JOIN articles a ON a.id = m.article_id
        WHERE m.story_id IN (SELECT story_id FROM surf) AND m.source_id IS NOT NULL
        GROUP BY m.story_id, m.source_id
    """, (run_id,))
    n_src = cur.rowcount
    cur.execute("""
        UPDATE analytics.story_sources s SET is_canonical_origin = true
        FROM (SELECT story_id, min(first_seen_at) mn FROM analytics.story_sources GROUP BY 1) e
        WHERE s.story_id = e.story_id AND s.first_seen_at = e.mn
    """)

    # --- story_geo: subject countries from article geo_primary ---
    cur.execute("TRUNCATE analytics.story_geo")
    cur.execute(f"""
        WITH {surf_cte},
        g AS (SELECT m.story_id, a.geo_primary country FROM analytics.story_cluster_members m
              JOIN articles a ON a.id = m.article_id
              WHERE m.story_id IN (SELECT story_id FROM surf) AND a.geo_primary IS NOT NULL AND a.geo_primary <> ''),
        cnt AS (SELECT story_id, country, count(*) c FROM g GROUP BY 1, 2)
        INSERT INTO analytics.story_geo (story_id, subject_countries, primary_country, country_spread, run_id)
        SELECT story_id,
               jsonb_agg(jsonb_build_object('country', country, 'mention_count', c) ORDER BY c DESC),
               (array_agg(country ORDER BY c DESC))[1],
               count(*), %s
        FROM cnt GROUP BY story_id
    """, (run_id,))
    n_geo = cur.rowcount

    # --- coverage status (the [UNVERIFIED] tag): fraction of members with each source extracted ---
    cur.execute("DELETE FROM analytics.story_enrichment_status")
    cur.execute(f"""
        WITH {surf_cte},
        mem AS (SELECT m.story_id, m.article_id FROM analytics.story_cluster_members m
                WHERE m.story_id IN (SELECT story_id FROM surf))
        INSERT INTO analytics.story_enrichment_status
          (story_id, members_total, claims_coverage, quotes_coverage, stances_coverage, geo_coverage, run_id)
        SELECT mem.story_id, count(*),
          round(avg((EXISTS (SELECT 1 FROM public.article_claims c  WHERE c.article_id = mem.article_id))::int), 3),
          round(avg((EXISTS (SELECT 1 FROM public.article_quotes q  WHERE q.article_id = mem.article_id))::int), 3),
          round(avg((EXISTS (SELECT 1 FROM public.article_stances s WHERE s.article_id = mem.article_id))::int), 3),
          round(avg((a.geo_primary IS NOT NULL AND a.geo_primary <> '')::int), 3),
          %s
        FROM mem JOIN articles a ON a.id = mem.article_id GROUP BY mem.story_id
    """, (run_id,))
    n_st = cur.rowcount
    sys.stderr.write(f"STRUCTURAL enriched (run_id={run_id}): timeline={n_tl} sources={n_src} "
                     f"geo={n_geo} status={n_st}\n")


def extraction(cur, run_id: int) -> None:
    surf_cte = f"surf AS (SELECT story_id FROM analytics.story_clusters WHERE {SURF})"

    # --- story_quotes: direct row-map from article_quotes (surfaced-only) ---
    cur.execute("TRUNCATE analytics.story_quotes")
    cur.execute(f"""
        WITH {surf_cte}
        INSERT INTO analytics.story_quotes
          (story_id, quote_text, quote_text_en, speaker, speaker_entity_id, article_id, is_direct, run_id)
        SELECT m.story_id, q.quote_text, q.quote_text_en, q.speaker_name, q.speaker_entity_id,
               q.article_id, q.is_direct, %s
        FROM analytics.story_cluster_members m
        JOIN public.article_quotes q ON q.article_id = m.article_id
        WHERE m.story_id IN (SELECT story_id FROM surf)
    """, (run_id,))
    n_q = cur.rowcount

    # --- story_stance: aggregate article_stances; sentiment carries n (mean-over-2 != over-40) ---
    cur.execute("TRUNCATE analytics.story_stance")
    cur.execute(f"""
        WITH {surf_cte},
        st AS (SELECT m.story_id, s.stance, s.intensity FROM analytics.story_cluster_members m
               JOIN public.article_stances s ON s.article_id = m.article_id
               WHERE m.story_id IN (SELECT story_id FROM surf) AND s.stance IS NOT NULL),
        dist AS (SELECT story_id, stance, count(*) c FROM st GROUP BY 1, 2),
        agg AS (SELECT story_id, round(avg(intensity)::numeric, 3) mean_int, count(*) tot FROM st GROUP BY 1)
        INSERT INTO analytics.story_stance (story_id, stance_distribution, sentiment, n_stances, run_id)
        SELECT d.story_id, jsonb_object_agg(d.stance, d.c),
               jsonb_build_object('mean_intensity', a.mean_int, 'n', a.tot), a.tot, %s
        FROM dist d JOIN agg a ON a.story_id = d.story_id
        GROUP BY d.story_id, a.mean_int, a.tot
    """, (run_id,))
    n_s = cur.rowcount

    # --- story_facts: B-minus conservative grouping (subject + unit + entity; under-merge when unsure) ---
    cur.execute("TRUNCATE analytics.story_facts")
    cur.execute(f"""
        WITH {surf_cte}
        SELECT m.story_id, c.subject_text, c.object_text, c.claim_text, c.subject_entity_id,
               c.article_id, a.collected_at
        FROM analytics.story_cluster_members m
        JOIN public.article_claims c ON c.article_id = m.article_id
        JOIN articles a ON a.id = m.article_id
        WHERE m.story_id IN (SELECT story_id FROM surf)
    """)
    # A-with-corroboration: the key INCLUDES the value, so identical values aggregate (N sources
    # assert the same number) and different values stay SEPARATE rows. NEVER a cross-value min->max
    # range — the B-minus grouping-integrity check (2026-06-03) found those were entity-keyed
    # collisions ("virat kohli 28->675" = runs vs balls vs totals), so divergence is deferred to a
    # measure-detection v1.1. value_min==value_max==value here; a consumer sees the distinct values
    # + corroboration counts and infers spread itself rather than us asserting a fabricated range.
    groups = defaultdict(list)  # (story, measure, unit, value) -> [(article_id, collected_at, claim_text)]
    for story_id, subj, obj, claim, ent, aid, coll in cur.fetchall():
        num, unit = extract_num_unit(obj)
        if num is None:
            continue
        measure = norm_measure(subj)
        if not measure:                 # un-keyable number (no subject) -> skip; never mis-group
            continue
        groups[(str(story_id), measure, unit, round(num, 4))].append((str(aid), coll, claim))
    rows = []
    for (sid, measure, unit, val), items in groups.items():
        cite = sorted({x[0] for x in items})
        sample = next((x[2] for x in items if x[2]), None)
        rows.append((sid, measure, unit, val, val, val, len(cite), cite,
                     len(cite) == 1, (sample or "")[:300], run_id))
    execute_values(cur, """
        INSERT INTO analytics.story_facts
          (story_id, fact_key, unit, value_min, value_max, value_latest, member_count,
           citing_article_ids, single_source, sample_claim, run_id)
        VALUES %s
    """, rows, template="(%s,%s,%s,%s,%s,%s,%s,%s::uuid[],%s,%s,%s)", page_size=2000)
    n_f = len(rows)

    # --- update coverage status counts (Phase A populated coverage; Phase B fills the counts) ---
    cur.execute("""
        UPDATE analytics.story_enrichment_status s SET
          facts_count  = coalesce((SELECT count(*) FROM analytics.story_facts  f WHERE f.story_id = s.story_id), 0),
          quotes_count = coalesce((SELECT count(*) FROM analytics.story_quotes q WHERE q.story_id = s.story_id), 0),
          stance_count = coalesce((SELECT n_stances FROM analytics.story_stance st WHERE st.story_id = s.story_id), 0)
    """)
    corrob = sum(1 for r in rows if not r[8])
    sys.stderr.write(f"EXTRACTION enriched (run_id={run_id}): quotes={n_q} stance={n_s} facts={n_f} "
                     f"(corroborated mc>=2: {corrob}, single-source: {n_f - corrob}) — A-with-corroboration, no fabricated ranges\n")


def main() -> int:
    dsn = os.environ.get("AB_DSN") or os.environ.get("DATABASE_URL_SYNC") or os.environ.get("DATABASE_URL")
    conn = psycopg2.connect(dsn)
    cur = conn.cursor()
    run_id = int(time.time())
    if PHASE in ("structural", "all"):
        structural(cur, run_id)
        conn.commit()
    if PHASE in ("extraction", "all"):
        extraction(cur, run_id)
        conn.commit()
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
