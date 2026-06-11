\echo === Total articles last 48h, by substrate_status ===
SELECT substrate_status, COUNT(*) AS n,
       ROUND(100.0*COUNT(*)/SUM(COUNT(*)) OVER (), 1) AS pct
  FROM articles
 WHERE collected_at >= NOW() - INTERVAL '48 hours'
 GROUP BY substrate_status ORDER BY n DESC;

\echo
\echo === Per-day ingest rate ===
SELECT date_trunc('day', collected_at) AS day,
       COUNT(*) AS articles,
       COUNT(DISTINCT source_id) AS sources,
       COUNT(*) FILTER (WHERE substrate_status='ok' AND extraction_version >= 3) AS v3_ok,
       COUNT(*) FILTER (WHERE labse_embedding IS NOT NULL) AS embedded
  FROM articles
 WHERE collected_at >= NOW() - INTERVAL '48 hours'
 GROUP BY 1 ORDER BY 1 DESC;

\echo
\echo === Downstream extraction counts for last-48h articles ===
WITH last48 AS (
  SELECT id FROM articles WHERE collected_at >= NOW() - INTERVAL '48 hours'
)
SELECT 'claims'   AS table, COUNT(*) AS rows,
       COUNT(DISTINCT ac.article_id) AS articles_with_data
  FROM article_claims ac WHERE ac.article_id IN (SELECT id FROM last48)
UNION ALL
SELECT 'quotes', COUNT(*), COUNT(DISTINCT aq.article_id)
  FROM article_quotes aq WHERE aq.article_id IN (SELECT id FROM last48)
UNION ALL
SELECT 'events', COUNT(*), COUNT(DISTINCT ae.article_id)
  FROM article_events ae WHERE ae.article_id IN (SELECT id FROM last48)
UNION ALL
SELECT 'locations', COUNT(*), COUNT(DISTINCT al.article_id)
  FROM article_locations al WHERE al.article_id IN (SELECT id FROM last48)
UNION ALL
SELECT 'numbers', COUNT(*), COUNT(DISTINCT an.article_id)
  FROM article_numbers an WHERE an.article_id IN (SELECT id FROM last48)
UNION ALL
SELECT 'stances', COUNT(*), COUNT(DISTINCT s.article_id)
  FROM article_stances s WHERE s.article_id IN (SELECT id FROM last48);

\echo
\echo === Top 10 most prolific sources last 48h ===
SELECT s.name AS source, COUNT(*) AS articles, a.language_detected AS lang
  FROM articles a JOIN sources s ON s.id=a.source_id
 WHERE a.collected_at >= NOW() - INTERVAL '48 hours'
 GROUP BY s.name, a.language_detected
 ORDER BY 2 DESC LIMIT 10;
