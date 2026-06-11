-- cross_source_agreement.sql — Layer 4 of the deep audit.
--
-- For event_clusters with ≥3 contributing sources, check whether articles
-- within the same cluster agree on key extracted fields. Disagreement
-- indicates inconsistency in extraction (or legitimate variation across
-- outlets).
--
-- All read-only.

\pset format aligned
\pset border 1
\pset null '·'

-- ============================================================================
-- 4A. Multi-source clusters — count + agreement on effective_event_date
-- ============================================================================
\echo
\echo ==== 4A. Multi-source clusters: event_date agreement ====
WITH cluster_dates AS (
  SELECT ec.id AS cluster_id, ec.article_count, ec.source_count,
         COUNT(DISTINCT ae.effective_event_date) AS distinct_dates,
         MIN(ae.effective_event_date) AS min_d,
         MAX(ae.effective_event_date) AS max_d
    FROM event_clusters ec
    JOIN article_events ae ON ae.event_cluster_id = ec.id
   WHERE ec.is_active AND ec.source_count >= 3
     AND ae.effective_event_date IS NOT NULL
   GROUP BY ec.id, ec.article_count, ec.source_count
)
SELECT
  COUNT(*) AS multi_source_clusters,
  COUNT(*) FILTER (WHERE distinct_dates = 1) AS perfect_agreement,
  COUNT(*) FILTER (WHERE distinct_dates = 2) AS one_disagreement,
  COUNT(*) FILTER (WHERE distinct_dates >= 3) AS many_disagreements,
  COUNT(*) FILTER (WHERE max_d - min_d > 30) AS spans_more_than_30days,
  ROUND(100.0 * COUNT(*) FILTER (WHERE distinct_dates = 1) / COUNT(*), 1) AS pct_perfect
  FROM cluster_dates;

-- ============================================================================
-- 4B. Per-cluster actor agreement (Jaccard within cluster)
-- ============================================================================
\echo
\echo ==== 4B. Per-cluster actor overlap (multi-source clusters) ====
WITH cluster_actors AS (
  SELECT ec.id AS cluster_id, ec.source_count,
         ae.id AS event_id,
         array_to_string(ae.actors, ',') AS actor_str
    FROM event_clusters ec
    JOIN article_events ae ON ae.event_cluster_id = ec.id
   WHERE ec.is_active AND ec.source_count >= 3
     AND ae.actors IS NOT NULL AND array_length(ae.actors, 1) > 0
),
pair_agreement AS (
  SELECT a.cluster_id,
         COUNT(*) AS n_events,
         COUNT(DISTINCT a.actor_str) AS distinct_actor_strings
    FROM cluster_actors a
   GROUP BY a.cluster_id
)
SELECT
  COUNT(*) AS multi_source_clusters,
  ROUND(AVG(n_events), 1) AS avg_events_per_cluster,
  ROUND(AVG(distinct_actor_strings), 1) AS avg_distinct_actor_strings,
  COUNT(*) FILTER (WHERE distinct_actor_strings = 1) AS one_actor_string,
  COUNT(*) FILTER (WHERE distinct_actor_strings::float / n_events > 0.5) AS high_actor_variance
  FROM pair_agreement;

-- ============================================================================
-- 4C. Location agreement within multi-source clusters
-- ============================================================================
\echo
\echo ==== 4C. Location agreement per cluster (multi-source) ====
WITH cluster_loc AS (
  SELECT ec.id AS cluster_id,
         COUNT(DISTINCT LOWER(al.location_text)) AS distinct_locs,
         COUNT(*) AS n_loc_rows
    FROM event_clusters ec
    JOIN article_events ae ON ae.event_cluster_id = ec.id
    JOIN article_locations al ON al.article_id = ae.article_id
   WHERE ec.is_active AND ec.source_count >= 3
     AND al.location_text IS NOT NULL
   GROUP BY ec.id
)
SELECT
  COUNT(*) AS clusters_with_locations,
  COUNT(*) FILTER (WHERE distinct_locs = 1) AS one_location,
  COUNT(*) FILTER (WHERE distinct_locs BETWEEN 2 AND 3) AS two_or_three_locs,
  COUNT(*) FILTER (WHERE distinct_locs > 3) AS many_locs
  FROM cluster_loc;

-- ============================================================================
-- 4D. Sample of clusters with HIGH disagreement (for manual review)
-- ============================================================================
\echo
\echo ==== 4D. Top 10 high-disagreement clusters ====
WITH cluster_metrics AS (
  SELECT ec.id, ec.canonical_description, ec.canonical_event_type,
         ec.article_count, ec.source_count,
         COUNT(DISTINCT ae.effective_event_date) AS distinct_dates,
         COUNT(DISTINCT array_to_string(ae.actors, ',')) AS distinct_actor_sets
    FROM event_clusters ec
    JOIN article_events ae ON ae.event_cluster_id = ec.id
   WHERE ec.is_active AND ec.source_count >= 3
   GROUP BY ec.id, ec.canonical_description, ec.canonical_event_type,
            ec.article_count, ec.source_count
)
SELECT canonical_event_type AS etype,
       article_count AS art_n, source_count AS src_n,
       distinct_dates AS d_dates, distinct_actor_sets AS d_actors,
       LEFT(canonical_description, 60) AS canonical
  FROM cluster_metrics
 WHERE distinct_dates > 1 OR distinct_actor_sets > 2
 ORDER BY (distinct_dates + distinct_actor_sets) DESC, article_count DESC
 LIMIT 10;
