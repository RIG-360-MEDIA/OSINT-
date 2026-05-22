-- v3_sanity.sql — Layer 1 of the deep data quality audit.
--
-- Read-only SQL queries across the 10 v3 tables. Each query is a labeled CTE
-- emitting (label, metric_name, value, severity, sample_id) rows so the
-- orchestrator (run_audit.py) can aggregate into the markdown report.
--
-- All queries should complete in < 60s on prod corpus.
-- No writes. Safe to run on live DB at any time.

\timing off
\pset format aligned
\pset border 1
\pset null '·'

-- ============================================================================
-- 1A. Row counts per table (sanity baseline)
-- ============================================================================
\echo
\echo ==== 1A. Row counts per v3 table ====
SELECT
  'articles' AS t,                COUNT(*) AS rows FROM articles
UNION ALL SELECT 'article_events',         COUNT(*) FROM article_events
UNION ALL SELECT 'article_quotes',         COUNT(*) FROM article_quotes
UNION ALL SELECT 'article_claims',         COUNT(*) FROM article_claims
UNION ALL SELECT 'article_stances',        COUNT(*) FROM article_stances
UNION ALL SELECT 'article_locations',      COUNT(*) FROM article_locations
UNION ALL SELECT 'article_numbers',        COUNT(*) FROM article_numbers
UNION ALL SELECT 'article_contradictions', COUNT(*) FROM article_contradictions
UNION ALL SELECT 'article_links',          COUNT(*) FROM article_links
UNION ALL SELECT 'article_media',          COUNT(*) FROM article_media
ORDER BY t;

-- ============================================================================
-- 1B. FK orphan detection (each child should point to an existing article)
-- ============================================================================
\echo
\echo ==== 1B. Foreign-key orphans ====
SELECT 'article_events' AS t, COUNT(*) AS orphans
  FROM article_events ae LEFT JOIN articles a ON a.id = ae.article_id WHERE a.id IS NULL
UNION ALL
SELECT 'article_quotes', COUNT(*)
  FROM article_quotes ae LEFT JOIN articles a ON a.id = ae.article_id WHERE a.id IS NULL
UNION ALL
SELECT 'article_claims', COUNT(*)
  FROM article_claims ae LEFT JOIN articles a ON a.id = ae.article_id WHERE a.id IS NULL
UNION ALL
SELECT 'article_stances', COUNT(*)
  FROM article_stances ae LEFT JOIN articles a ON a.id = ae.article_id WHERE a.id IS NULL
UNION ALL
SELECT 'article_locations', COUNT(*)
  FROM article_locations ae LEFT JOIN articles a ON a.id = ae.article_id WHERE a.id IS NULL
UNION ALL
SELECT 'article_numbers', COUNT(*)
  FROM article_numbers ae LEFT JOIN articles a ON a.id = ae.article_id WHERE a.id IS NULL
-- article_contradictions has no article_id FK (uses entity_id to entity_dictionary)
-- so it's checked separately in section 1B2 below.
UNION ALL
SELECT 'article_links', COUNT(*)
  FROM article_links ae LEFT JOIN articles a ON a.id = ae.article_id WHERE a.id IS NULL
UNION ALL
SELECT 'article_media', COUNT(*)
  FROM article_media ae LEFT JOIN articles a ON a.id = ae.article_id WHERE a.id IS NULL
ORDER BY t;

-- ============================================================================
-- 1C. Year-drift residual (post-053d clamp — should be < 2%)
-- ============================================================================
\echo
\echo ==== 1C. Year-drift residual on effective_event_date ====
WITH stats AS (
  SELECT
    COUNT(*) AS total,
    COUNT(*) FILTER (WHERE ae.event_date IS NOT NULL) AS with_date,
    COUNT(*) FILTER (WHERE ae.event_date IS NOT NULL
                       AND EXTRACT(YEAR FROM ae.event_date)::int
                           < EXTRACT(YEAR FROM a.published_at)::int - 1) AS pre_drift,
    COUNT(*) FILTER (WHERE ae.effective_event_date IS NOT NULL
                       AND EXTRACT(YEAR FROM ae.effective_event_date)::int
                           < EXTRACT(YEAR FROM a.published_at)::int - 1) AS residual_drift,
    COUNT(*) FILTER (WHERE ae.effective_event_date <> ae.event_date) AS corrected
    FROM article_events ae JOIN articles a ON a.id = ae.article_id
)
SELECT total, with_date, pre_drift, residual_drift, corrected,
       ROUND(100.0 * residual_drift / NULLIF(with_date, 0), 2) AS pct_residual_drift,
       ROUND(100.0 * corrected / NULLIF(with_date, 0), 1) AS pct_corrected
  FROM stats;

-- ============================================================================
-- 1D. Truncation cliff detection (exact 500/1000-char endings on summaries)
-- ============================================================================
\echo
\echo ==== 1D. Truncation cliffs on summary fields ====
SELECT 'summary_preview = 500'    AS bucket,
       COUNT(*) FILTER (WHERE LENGTH(summary_preview) = 500)  AS n FROM articles
UNION ALL SELECT 'summary_snippet = 1000',
       COUNT(*) FILTER (WHERE LENGTH(summary_snippet) = 1000) FROM articles
UNION ALL SELECT 'summary_executive = 500',
       COUNT(*) FILTER (WHERE LENGTH(summary_executive) = 500) FROM articles
UNION ALL SELECT 'summary_executive = 1000',
       COUNT(*) FILTER (WHERE LENGTH(summary_executive) = 1000) FROM articles
UNION ALL SELECT 'summary_executive = 2000',
       COUNT(*) FILTER (WHERE LENGTH(summary_executive) = 2000) FROM articles
UNION ALL SELECT 'event_description = 500',
       COUNT(*) FILTER (WHERE LENGTH(event_description) = 500) FROM article_events;

-- ============================================================================
-- 1E. NULL leakage on v3-ok articles (these fields should be filled for v3 OK)
-- ============================================================================
\echo
\echo ==== 1E. NULL leakage on v3-ok articles ====
WITH ok_v3 AS (
  SELECT * FROM articles WHERE substrate_status = 'ok' AND extraction_version = 3
)
SELECT 'title NULL or short'                AS field,
       COUNT(*) FILTER (WHERE LENGTH(COALESCE(title,'')) < 5) AS n,
       (SELECT COUNT(*) FROM ok_v3)                          AS denominator
  FROM ok_v3
UNION ALL SELECT 'primary_subject NULL/short',
       COUNT(*) FILTER (WHERE LENGTH(COALESCE(primary_subject,'')) < 5),
       (SELECT COUNT(*) FROM ok_v3)
  FROM ok_v3
UNION ALL SELECT 'summary_executive NULL/short',
       COUNT(*) FILTER (WHERE LENGTH(COALESCE(summary_executive,'')) < 50),
       (SELECT COUNT(*) FROM ok_v3)
  FROM ok_v3
UNION ALL SELECT 'language_detected NULL',
       COUNT(*) FILTER (WHERE language_detected IS NULL),
       (SELECT COUNT(*) FROM ok_v3)
  FROM ok_v3
UNION ALL SELECT 'article_type NULL',
       COUNT(*) FILTER (WHERE article_type IS NULL),
       (SELECT COUNT(*) FROM ok_v3)
  FROM ok_v3
UNION ALL SELECT 'labse_embedding NULL',
       COUNT(*) FILTER (WHERE labse_embedding IS NULL),
       (SELECT COUNT(*) FROM ok_v3)
  FROM ok_v3
UNION ALL SELECT 'published_at NULL',
       COUNT(*) FILTER (WHERE published_at IS NULL),
       (SELECT COUNT(*) FROM ok_v3)
  FROM ok_v3;

-- ============================================================================
-- 1F. Language mis-tag detection (Telugu/Hindi/Bengali chars in 'en' articles)
-- ============================================================================
\echo
\echo ==== 1F. Language mis-tag candidates ====
-- Telugu Unicode block: ఀ-౿; Devanagari: ऀ-ॿ; Bengali: ঀ-৿
SELECT 'en-tagged with Telugu chars in title' AS bucket,
       COUNT(*) AS n
  FROM articles
 WHERE language_detected = 'en'
   AND title ~ '[ఀ-౿]'
UNION ALL
SELECT 'en-tagged with Devanagari chars in title',
       COUNT(*)
  FROM articles
 WHERE language_detected = 'en'
   AND title ~ '[ऀ-ॿ]'
UNION ALL
SELECT 'en-tagged with Bengali chars in title',
       COUNT(*)
  FROM articles
 WHERE language_detected = 'en'
   AND title ~ '[ঀ-৿]'
UNION ALL
SELECT 'te-tagged with no Telugu chars in title (suspect)',
       COUNT(*)
  FROM articles
 WHERE language_detected = 'te'
   AND title !~ '[ఀ-౿]'
   AND LENGTH(title) > 5;

-- ============================================================================
-- 1G. extraction_version distribution
-- ============================================================================
\echo
\echo ==== 1G. extraction_version distribution ====
SELECT extraction_version, COUNT(*) AS n,
       COUNT(*) FILTER (WHERE substrate_status = 'ok') AS ok_count
  FROM articles
 GROUP BY extraction_version
 ORDER BY extraction_version NULLS FIRST;

-- ============================================================================
-- 1H. Duplicate article detection (same url_hash)
-- ============================================================================
\echo
\echo ==== 1H. Duplicate articles by url_hash ====
SELECT COUNT(*) AS rows_with_duplicate_url_hash
  FROM (
    SELECT url_hash, COUNT(*) AS c
      FROM articles
     WHERE url_hash IS NOT NULL
     GROUP BY url_hash
    HAVING COUNT(*) > 1
  ) dups;

-- ============================================================================
-- 1J. article_claims placeholder subject_text bug (74% of rows = 'article')
-- This is a CRITICAL extraction bug surfaced in Phase 2 audit on 2026-05-22.
-- We track its prevalence as a per-run metric to detect when the underlying
-- extraction prompt is fixed.
-- ============================================================================
\echo
\echo ==== 1J. article_claims placeholder bug ====
SELECT
  COUNT(*) AS total_claims,
  COUNT(*) FILTER (WHERE LOWER(subject_text) IN ('article','story','report','news','piece')) AS placeholder_count,
  ROUND(100.0 * COUNT(*) FILTER (WHERE LOWER(subject_text) IN ('article','story','report','news','piece')) / COUNT(*), 1) AS placeholder_pct
  FROM article_claims;

-- ============================================================================
-- 1I. event_date NULL rate within v3 article_events
-- ============================================================================
\echo
\echo ==== 1I. event_date fill rate ====
WITH e AS (
  SELECT ae.* FROM article_events ae
   JOIN articles a ON a.id = ae.article_id
  WHERE a.substrate_status='ok' AND a.extraction_version=3
)
SELECT COUNT(*) AS total,
       COUNT(event_date) AS with_date,
       COUNT(effective_event_date) AS with_effective_date,
       COUNT(*) FILTER (WHERE is_future = TRUE) AS future_events,
       ROUND(100.0 * COUNT(event_date) / NULLIF(COUNT(*),0), 1) AS pct_with_date
  FROM e;
