-- cutover_story_clustering.sql
--
-- MANUAL SQL — DO NOT auto-run. Each section is gated by a confirm step.
-- Run after:
--   1. Migration 051_story_clustering_v2.sql has been applied.
--   2. The new Celery tasks (story_cluster_new_articles +
--      story_cluster_consolidate) have been deployed and validated on
--      a 500-article sample.
--   3. The OLD tasks (assign-threads-every-5-min,
--      nightly-thread-recluster) have been removed from the Beat
--      schedule.
--
-- Steps in order:
--   A. Confirm no concurrent old-task activity (pg_stat_activity).
--   B. Disable the legacy v1 threads (read-only state).
--   C. Null out articles.thread_id where it points to v1 rows.
--   D. TRUNCATE the legacy rows (cluster_version = 1).
--   E. Sanity counts.
--
-- Roll-forward only — backup the table first if you want a fallback.

\echo '=== A. Sessions running the old engine? ==='
SELECT pid, state, query_start, LEFT(query, 80) AS query
  FROM pg_stat_activity
 WHERE query ILIKE '%story_threads%'
   AND state <> 'idle';

\echo
\echo '=== B. Pre-cutover counts ==='
SELECT cluster_version,
       COUNT(*) AS threads,
       COUNT(*) FILTER (WHERE is_active) AS active
  FROM story_threads
 GROUP BY cluster_version
 ORDER BY cluster_version;

SELECT 'articles linked to v1' AS what,
       COUNT(*) AS n
  FROM articles a
  JOIN story_threads st ON st.id = a.thread_id
 WHERE st.cluster_version = 1;

\echo
\echo '=== C. Begin transaction ==='
BEGIN;

-- C1. NULL out articles pointing to v1 threads.
UPDATE articles a
   SET thread_id = NULL
  FROM story_threads st
 WHERE st.id = a.thread_id
   AND st.cluster_version = 1;

-- C2. Mark v1 threads inactive (defensive — they'll be deleted next
--     but if anything else still queries them we want is_active=FALSE).
UPDATE story_threads
   SET is_active = FALSE
 WHERE cluster_version = 1;

-- C3. Delete v1 rows.
DELETE FROM story_threads
 WHERE cluster_version = 1;

\echo
\echo '=== D. Post-cutover counts (still in transaction) ==='
SELECT cluster_version,
       COUNT(*) AS threads,
       COUNT(*) FILTER (WHERE is_active) AS active
  FROM story_threads
 GROUP BY cluster_version;

SELECT 'articles with thread_id'  AS what, COUNT(thread_id) AS n FROM articles
UNION ALL
SELECT 'articles WITHOUT thread_id', COUNT(*) FILTER (WHERE thread_id IS NULL) FROM articles;

\echo
\echo '=== E. Inspect, then either COMMIT or ROLLBACK ==='
-- COMMIT;
-- ROLLBACK;
