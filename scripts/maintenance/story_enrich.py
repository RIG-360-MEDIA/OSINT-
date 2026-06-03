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
import sys
import time

import psycopg2

PHASE = os.environ.get("PHASE", "structural")
BREAKING_VELOCITY = float(os.environ.get("BREAKING_VELOCITY", "10"))
SURF = "(NOT is_template_family AND (independent_source_count >= 3 OR rescued_from_story_id IS NOT NULL))"


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


def main() -> int:
    dsn = os.environ.get("AB_DSN") or os.environ.get("DATABASE_URL_SYNC") or os.environ.get("DATABASE_URL")
    conn = psycopg2.connect(dsn)
    cur = conn.cursor()
    run_id = int(time.time())
    if PHASE in ("structural", "all"):
        structural(cur, run_id)
        conn.commit()
    if PHASE in ("extraction", "all"):
        sys.stderr.write("PHASE extraction not in this build (facts/quotes/stance ship in Phase B)\n")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
