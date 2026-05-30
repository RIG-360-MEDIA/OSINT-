-- 086_freshness_views.sql
-- =====================================================================
-- Worldwide Phase 0a: freshness instrumentation.
--
-- SQL views the team (and any BI tool on analytics_user) can watch to
-- see how current the pipeline is. This is the dependency the clustering
-- launch is GATED on ("no flying blind"). Views are stored queries — no
-- data lock, safe to (re)apply anytime.
--
--   v_freshness_now            one-row real-time snapshot
--   v_freshness_coverage_by_age embed/nlp/substrate coverage by age
--   v_freshness_pipeline_lag    ingest->embed / ingest->substrate p50/p95
--
-- NOTE: the embed-lag row stays empty until embedded_at starts flowing
-- (migration 085 + the embed code deploy). That is expected and honest —
-- the view will light up as new vectors arrive.
-- =====================================================================

CREATE OR REPLACE VIEW v_freshness_now AS
SELECT
  (SELECT max(collected_at) FROM articles)                                              AS newest_article,
  (SELECT round(EXTRACT(EPOCH FROM (now()-max(collected_at)))/60)::int FROM articles)   AS newest_age_min,
  (SELECT count(*) FROM articles WHERE collected_at > now()-interval '1 hour')          AS ingested_1h,
  (SELECT count(*) FROM articles WHERE collected_at > now()-interval '24 hours')        AS ingested_24h,
  (SELECT round(100.0*count(labse_embedding)/NULLIF(count(*),0),1)
     FROM articles WHERE collected_at > now()-interval '24 hours')                      AS pct_embedded_24h,
  (SELECT count(*) FROM articles WHERE nlp_processed = FALSE)                           AS nlp_pending,
  (SELECT count(*) FROM articles WHERE labse_embedding IS NOT NULL)                     AS vectors_total,
  (SELECT count(*) FROM articles WHERE embedding_revision IS NOT NULL)                  AS vectors_with_provenance;

CREATE OR REPLACE VIEW v_freshness_coverage_by_age AS
SELECT
  CASE WHEN collected_at > now()-interval '2 days'  THEN '0-2d'
       WHEN collected_at > now()-interval '7 days'  THEN '2-7d'
       WHEN collected_at > now()-interval '14 days' THEN '7-14d'
       ELSE '14d+' END                                          AS bucket,
  count(*)                                                      AS total,
  count(labse_embedding)                                        AS embedded,
  round(100.0*count(labse_embedding)/NULLIF(count(*),0),1)      AS pct_embedded,
  count(*) FILTER (WHERE nlp_processed)                         AS nlp_done,
  count(*) FILTER (WHERE substrate_status = 'ok')               AS substrate_ok
FROM articles
GROUP BY 1
ORDER BY min(collected_at) DESC;

CREATE OR REPLACE VIEW v_freshness_pipeline_lag AS
SELECT 'embed'::text AS stage,
       count(*) AS n_24h,
       round(percentile_cont(0.5)  WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (embedded_at-collected_at))/60)::numeric,1) AS p50_min,
       round(percentile_cont(0.95) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (embedded_at-collected_at))/60)::numeric,1) AS p95_min
  FROM articles
 WHERE embedded_at IS NOT NULL AND collected_at > now()-interval '24 hours'
UNION ALL
SELECT 'substrate',
       count(*),
       round(percentile_cont(0.5)  WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (substrate_processed_at-collected_at))/60)::numeric,1),
       round(percentile_cont(0.95) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (substrate_processed_at-collected_at))/60)::numeric,1)
  FROM articles
 WHERE substrate_status = 'ok' AND substrate_processed_at > now()-interval '24 hours';

GRANT SELECT ON v_freshness_now, v_freshness_coverage_by_age, v_freshness_pipeline_lag TO analytics_user;
GRANT SELECT ON v_freshness_now, v_freshness_coverage_by_age, v_freshness_pipeline_lag TO rigwire_app;
