-- known_bug_probes.sql — Layer 6 of the deep audit.
--
-- Targeted SQL probes for known bug patterns we've discovered during
-- diagnostic work. Each probe asks "does this specific failure mode
-- still appear?" — useful as regression checks once fixes ship.
--
-- Each probe should:
--   1. Be quick (< 5 sec)
--   2. Return a single-row count of how many rows match the bug pattern
--   3. Have a clear "should be 0 after fix" expectation
--
-- All read-only.

\pset format aligned
\pset border 1

-- ============================================================================
-- 6A. PLACEHOLDER SUBJECTS — article_claims.subject_text = 'article' etc.
-- Bug found 2026-05-22. Expected behavior: 0 placeholder rows after prompt fix.
-- ============================================================================
\echo
\echo ==== 6A. article_claims placeholder subjects ====
SELECT 'literal "article"' AS pattern, COUNT(*) AS n FROM article_claims
 WHERE LOWER(subject_text) = 'article'
UNION ALL
SELECT 'literal "story" or "report"' , COUNT(*) FROM article_claims
 WHERE LOWER(subject_text) IN ('story', 'report', 'piece', 'news')
UNION ALL
SELECT 'empty / whitespace-only', COUNT(*) FROM article_claims
 WHERE LENGTH(COALESCE(TRIM(subject_text), '')) = 0;

-- ============================================================================
-- 6B. YEAR DRIFT (post-clamp residual)
-- Bug fixed via migration 053d. Expected: all residual explainable.
-- ============================================================================
\echo
\echo ==== 6B. Year-drift residual breakdown ====
WITH residual AS (
  SELECT ae.is_future,
         ae.effective_event_date < a.published_at::date - INTERVAL '20 years' AS very_old,
         EXTRACT(MONTH FROM ae.event_date)::int = 2
           AND EXTRACT(DAY FROM ae.event_date)::int = 29 AS is_feb29
    FROM article_events ae JOIN articles a ON a.id = ae.article_id
   WHERE ae.event_date IS NOT NULL
     AND ae.effective_event_date IS NOT NULL
     AND EXTRACT(YEAR FROM ae.effective_event_date)::int
         < EXTRACT(YEAR FROM a.published_at)::int - 1
)
SELECT
  COUNT(*) AS total_residual,
  COUNT(*) FILTER (WHERE is_future) AS future_explained,
  COUNT(*) FILTER (WHERE very_old) AS old_explained,
  COUNT(*) FILTER (WHERE is_feb29) AS feb29_explained,
  COUNT(*) FILTER (WHERE NOT is_future AND NOT very_old AND NOT is_feb29) AS unexplained
  FROM residual;

-- ============================================================================
-- 6C. is_future flag inconsistency
-- LLM flagged "this is future" but extracted past date. Found Phase 1.
-- ============================================================================
\echo
\echo ==== 6C. is_future flag = TRUE but event in past ====
SELECT COUNT(*) AS contradictory_is_future
  FROM article_events ae JOIN articles a ON a.id = ae.article_id
 WHERE ae.is_future = TRUE
   AND ae.effective_event_date < a.published_at::date - INTERVAL '60 days';

-- ============================================================================
-- 6D. LANGUAGE MIS-TAGS — Hindi/Telugu chars in 'en' articles
-- ============================================================================
\echo
\echo ==== 6D. Language mis-tags ====
SELECT 'en+Telugu' AS pattern, COUNT(*) AS n
  FROM articles WHERE language_detected='en' AND title ~ '[ఀ-౿]'
UNION ALL SELECT 'en+Devanagari', COUNT(*)
  FROM articles WHERE language_detected='en' AND title ~ '[ऀ-ॿ]'
UNION ALL SELECT 'en+Bengali', COUNT(*)
  FROM articles WHERE language_detected='en' AND title ~ '[ঀ-৿]'
UNION ALL SELECT 'te+no Telugu', COUNT(*)
  FROM articles WHERE language_detected='te' AND title !~ '[ఀ-౿]' AND LENGTH(title) > 5;

-- ============================================================================
-- 6E. TRUNCATION CLIFFS on summary_executive
-- ============================================================================
\echo
\echo ==== 6E. Summary truncation cliffs ====
SELECT '500-char cliff' AS pattern, COUNT(*) AS n
  FROM articles WHERE LENGTH(summary_executive) = 500
UNION ALL SELECT '1000-char cliff', COUNT(*)
  FROM articles WHERE LENGTH(summary_executive) = 1000
UNION ALL SELECT '2000-char cliff', COUNT(*)
  FROM articles WHERE LENGTH(summary_executive) = 2000;

-- ============================================================================
-- 6F. EMBEDDING COLLISIONS — articles with identical labse_embedding
-- (Bug found earlier in session: ~15K articles share collapsed vectors)
-- ============================================================================
\echo
\echo ==== 6F. labse_embedding collisions ====
SELECT
  COUNT(*) AS total_v3_with_embedding,
  COUNT(DISTINCT md5(labse_embedding::text)) AS distinct_vectors,
  COUNT(*) - COUNT(DISTINCT md5(labse_embedding::text)) AS dup_articles
  FROM articles
 WHERE substrate_status='ok' AND extraction_version=3
   AND labse_embedding IS NOT NULL;

-- ============================================================================
-- 6G. v3-ok articles missing critical fields
-- Should always be near zero for substrate_status='ok' rows.
-- ============================================================================
\echo
\echo ==== 6G. v3-ok with missing critical fields ====
SELECT
  COUNT(*) AS total_v3_ok,
  COUNT(*) FILTER (WHERE primary_subject IS NULL OR LENGTH(primary_subject) < 5) AS missing_subject,
  COUNT(*) FILTER (WHERE summary_executive IS NULL OR LENGTH(summary_executive) < 50) AS missing_summary,
  COUNT(*) FILTER (WHERE labse_embedding IS NULL) AS missing_embedding,
  COUNT(*) FILTER (WHERE published_at IS NULL) AS missing_published_at,
  COUNT(*) FILTER (WHERE article_type IS NULL) AS missing_article_type
  FROM articles
 WHERE substrate_status='ok' AND extraction_version=3;

-- ============================================================================
-- 6H. SOURCES WITH NO SUMMARY — sources that consistently produce empty summaries
-- ============================================================================
\echo
\echo ==== 6H. Sources where summary_executive is mostly NULL (>=10 articles) ====
WITH src AS (
  SELECT s.name, COUNT(*) AS total,
         COUNT(*) FILTER (WHERE a.summary_executive IS NULL OR LENGTH(a.summary_executive) < 50) AS missing
    FROM articles a JOIN sources s ON s.id = a.source_id
   WHERE a.substrate_status='ok' AND a.extraction_version=3
   GROUP BY s.name
  HAVING COUNT(*) >= 10
)
SELECT name AS source, total, missing,
       ROUND(100.0 * missing / total, 1) AS missing_pct
  FROM src
 WHERE missing > 0
 ORDER BY missing_pct DESC, total DESC
 LIMIT 10;
