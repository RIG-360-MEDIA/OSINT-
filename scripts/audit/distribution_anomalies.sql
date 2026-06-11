-- distribution_anomalies.sql — Layer 3 of the deep audit.
--
-- Find per-source, per-day, per-extraction-version outliers in field
-- distributions. Helps spot scraper regressions, prompt regressions, and
-- bad-actor sources.
--
-- All queries are read-only and use percentile/z-score aggregates.

\pset format aligned
\pset border 1
\pset null '·'

-- ============================================================================
-- 3A. Per-source field-fill scorecard (last 30 days of articles)
-- Sources that drop below 50% on important fields are flagged
-- ============================================================================
\echo
\echo ==== 3A. Per-source field-fill (30d, sources with >=20 articles) ====
WITH base AS (
  SELECT a.id, s.name AS source, a.extraction_version,
         CASE WHEN LENGTH(COALESCE(a.title,'')) > 5 THEN 1 ELSE 0 END AS f_title,
         CASE WHEN LENGTH(COALESCE(a.primary_subject,'')) > 5 THEN 1 ELSE 0 END AS f_subject,
         CASE WHEN LENGTH(COALESCE(a.summary_executive,'')) > 50 THEN 1 ELSE 0 END AS f_summary,
         CASE WHEN a.labse_embedding IS NOT NULL THEN 1 ELSE 0 END AS f_embedding,
         CASE WHEN a.published_at IS NOT NULL THEN 1 ELSE 0 END AS f_pubdate,
         CASE WHEN a.language_detected IS NOT NULL THEN 1 ELSE 0 END AS f_lang
    FROM articles a JOIN sources s ON s.id = a.source_id
   WHERE a.collected_at > NOW() - INTERVAL '30 days'
), agg AS (
  SELECT source, COUNT(*) AS n,
         ROUND(100.0 * AVG(f_title), 1) AS title_pct,
         ROUND(100.0 * AVG(f_subject), 1) AS subject_pct,
         ROUND(100.0 * AVG(f_summary), 1) AS summary_pct,
         ROUND(100.0 * AVG(f_embedding), 1) AS emb_pct,
         ROUND(100.0 * AVG(f_pubdate), 1) AS pub_pct,
         ROUND(100.0 * AVG(f_lang), 1) AS lang_pct
    FROM base GROUP BY source HAVING COUNT(*) >= 20
)
SELECT source, n, title_pct, subject_pct, summary_pct, emb_pct, pub_pct, lang_pct
  FROM agg
 ORDER BY (summary_pct + emb_pct + pub_pct) ASC
 LIMIT 25;

-- ============================================================================
-- 3B. Per-day v3 extraction quality (last 14 days)
-- Helps spot extraction quality drops day over day
-- ============================================================================
\echo
\echo ==== 3B. Per-day v3-ok counts (last 14 days) ====
SELECT a.collected_at::date AS d,
       COUNT(*) AS total,
       COUNT(*) FILTER (WHERE a.substrate_status='ok' AND a.extraction_version=3) AS v3_ok,
       COUNT(*) FILTER (WHERE a.substrate_status='pending') AS pending,
       COUNT(*) FILTER (WHERE a.substrate_status='fetch_failed') AS fetch_failed,
       ROUND(100.0 * COUNT(*) FILTER (WHERE a.substrate_status='ok'
                                       AND a.extraction_version=3) / COUNT(*), 1) AS pct_v3_ok
  FROM articles a
 WHERE a.collected_at > NOW() - INTERVAL '14 days'
 GROUP BY 1 ORDER BY 1 DESC;

-- ============================================================================
-- 3C. Summary length distribution outliers
-- ============================================================================
\echo
\echo ==== 3C. summary_executive length distribution (v3-ok) ====
WITH lens AS (
  SELECT LENGTH(summary_executive) AS L
    FROM articles
   WHERE substrate_status='ok' AND extraction_version=3
     AND summary_executive IS NOT NULL
)
SELECT
  COUNT(*) AS n,
  ROUND(AVG(L)) AS avg_len,
  PERCENTILE_CONT(0.05) WITHIN GROUP (ORDER BY L)::int AS p5,
  PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY L)::int AS p50,
  PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY L)::int AS p95,
  PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY L)::int AS p99,
  MAX(L) AS max_len,
  COUNT(*) FILTER (WHERE L < 80) AS very_short,
  COUNT(*) FILTER (WHERE L = 500) AS trunc_500,
  COUNT(*) FILTER (WHERE L = 1000) AS trunc_1000
  FROM lens;

-- ============================================================================
-- 3D. Events-per-article distribution outliers
-- ============================================================================
\echo
\echo ==== 3D. Events per article distribution ====
WITH e_per AS (
  SELECT a.id, COUNT(ae.id) AS n_events
    FROM articles a LEFT JOIN article_events ae ON ae.article_id = a.id
   WHERE a.substrate_status='ok' AND a.extraction_version=3
   GROUP BY a.id
)
SELECT n_events, COUNT(*) AS articles
  FROM e_per
 GROUP BY n_events
 ORDER BY n_events
 LIMIT 25;

-- ============================================================================
-- 3E. is_future flag inconsistency (events flagged future with past dates)
-- This is a known bug surfaced in Phase 1 — re-quantify here
-- ============================================================================
\echo
\echo ==== 3E. is_future logical inconsistencies ====
SELECT
  COUNT(*) FILTER (WHERE ae.is_future = TRUE
                     AND ae.effective_event_date < a.published_at::date - INTERVAL '60 days')
    AS future_flag_but_past_event,
  COUNT(*) FILTER (WHERE ae.is_future = FALSE
                     AND ae.effective_event_date > a.published_at::date + INTERVAL '60 days')
    AS past_flag_but_future_event,
  COUNT(*) AS total_events_with_date
  FROM article_events ae JOIN articles a ON a.id = ae.article_id
 WHERE ae.effective_event_date IS NOT NULL
   AND a.published_at IS NOT NULL;

-- ============================================================================
-- 3F. extraction_version × substrate_status crosstab
-- ============================================================================
\echo
\echo ==== 3F. extraction_version x substrate_status ====
SELECT extraction_version, substrate_status, COUNT(*) AS n
  FROM articles
 WHERE collected_at > NOW() - INTERVAL '30 days'
 GROUP BY 1, 2
 ORDER BY 1, 2;

-- ============================================================================
-- 3G. Sources that suddenly went dark (last seen > 7 days but had > 100 articles)
-- ============================================================================
\echo
\echo ==== 3G. Possibly-stalled sources (>=100 articles, no news in 7+ days) ====
WITH src_stats AS (
  SELECT s.name AS source, COUNT(*) AS total,
         MAX(a.collected_at) AS last_seen
    FROM articles a JOIN sources s ON s.id = a.source_id
   GROUP BY s.name
)
SELECT source, total, last_seen::date AS last_seen
  FROM src_stats
 WHERE total >= 100
   AND last_seen < NOW() - INTERVAL '7 days'
 ORDER BY last_seen ASC
 LIMIT 25;
