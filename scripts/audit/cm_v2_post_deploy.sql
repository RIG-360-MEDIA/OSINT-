-- cm_v2_post_deploy.sql
--
-- Single-shot health check for everything the CM Page v2 plan adds.
-- Run with:
--
--   docker exec -i rig-postgres psql -U rig -d rig \
--     -f /sql/cm_v2_post_deploy.sql
--
-- Each section returns a single row with a label + actual + expected
-- so the operator can eyeball pass / fail. None of the queries write;
-- safe to run any time.

\echo '== Phase 0 / Phase 1 — district resolution spine =='
SELECT
  'districts'                 AS table,
  COUNT(*)                     AS row_count,
  'expect >= 33 (TG) + 26 (AP) = 59' AS expected
FROM districts;

SELECT
  'districts.state_code'       AS column,
  COUNT(*) FILTER (WHERE state_code = 'TG') AS tg,
  COUNT(*) FILTER (WHERE state_code = 'AP') AS ap,
  COUNT(*) FILTER (WHERE state_code IS NULL) AS null_state,
  'expect tg >= 33, ap >= 26, null_state = 0' AS expected
FROM districts;

SELECT
  'article_districts'          AS table,
  COUNT(*)                     AS row_count,
  COUNT(DISTINCT article_id)   AS articles_tagged,
  'expect articles_tagged > 0.5 * articles.nlp_processed=true' AS expected
FROM article_districts;

\echo '== Phase 1 — assembly_constituencies (seed) =='
SELECT
  'assembly_constituencies'    AS table,
  COUNT(*)                     AS row_count,
  COUNT(*) FILTER (WHERE state_code = 'TG') AS tg,
  COUNT(*) FILTER (WHERE state_code = 'AP') AS ap,
  'expect tg = 119 once full seed loads' AS expected
FROM assembly_constituencies;

\echo '== Phase 3 — external sources =='
SELECT
  source_id,
  last_success_at,
  last_failure_at,
  consecutive_failures,
  rows_last_run,
  CASE
    WHEN last_success_at IS NULL THEN 'never-succeeded'
    WHEN last_success_at < NOW() - INTERVAL '24 hours' THEN 'STALE'
    ELSE 'fresh'
  END AS health
FROM source_run_health
ORDER BY source_id;

SELECT 'mandi_prices'         AS tbl, COUNT(*) AS rows FROM mandi_prices;
SELECT 'air_quality_readings' AS tbl, COUNT(*) AS rows FROM air_quality_readings;
SELECT 'weather_warnings'     AS tbl, COUNT(*) AS rows FROM weather_warnings;
SELECT 'power_grid_status'    AS tbl, COUNT(*) AS rows FROM power_grid_status;
SELECT 'welfare_coverage'     AS tbl, COUNT(*) AS rows FROM welfare_coverage;
SELECT 'acled_events'         AS tbl, COUNT(*) AS rows FROM acled_events;

\echo '== Phase 3 — atlas materialised views (each must be populated) =='
SELECT 'mv_district_news_volume_24h'    AS mv, COUNT(*) AS rows FROM mv_district_news_volume_24h;
SELECT 'mv_district_sentiment_24h'      AS mv, COUNT(*) AS rows FROM mv_district_sentiment_24h;
SELECT 'mv_district_acled_7d'           AS mv, COUNT(*) AS rows FROM mv_district_acled_7d;
SELECT 'mv_district_mandi_volatility_30d' AS mv, COUNT(*) AS rows FROM mv_district_mandi_volatility_30d;
SELECT 'mv_district_welfare_coverage'   AS mv, COUNT(*) AS rows FROM mv_district_welfare_coverage;
SELECT 'mv_district_power_stress'       AS mv, COUNT(*) AS rows FROM mv_district_power_stress;
SELECT 'mv_district_stability_composite' AS mv, COUNT(*) AS rows FROM mv_district_stability_composite;

\echo '== Phase 4 — LLM auto-publish stack =='
SELECT
  'cm_lead_headlines'          AS tbl,
  COUNT(*)                     AS rows_total,
  COUNT(*) FILTER (WHERE generated_at > NOW() - INTERVAL '6 hours') AS rows_last_6h,
  ROUND(100.0 *
    COUNT(*) FILTER (WHERE validated)
    / NULLIF(COUNT(*), 0), 1)  AS pct_validated,
  'expect rows_last_6h > 0, pct_validated > 95' AS expected
FROM cm_lead_headlines;

SELECT
  'cm_analysis_drafts'         AS tbl,
  status,
  COUNT(*)                     AS rows
FROM cm_analysis_drafts
GROUP BY status
ORDER BY status;

SELECT
  'cm_action_queue'            AS tbl,
  source_type,
  status,
  COUNT(*)                     AS rows
FROM cm_action_queue
GROUP BY source_type, status
ORDER BY source_type, status;

\echo '== Phase 4 — cite-ID validation rate (target > 95%) =='
SELECT
  'cm_lead_headlines.cite_validation' AS metric,
  ROUND(100.0 *
    COUNT(*) FILTER (WHERE validated)
    / NULLIF(COUNT(*), 0), 1)  AS pct_validated,
  COUNT(*)                     AS sample_size
FROM cm_lead_headlines
WHERE generated_at > NOW() - INTERVAL '24 hours';

\echo '== Done =='
