\echo === Articles ingested per hour, last 6 hours ===
SELECT date_trunc('hour', collected_at) AS hour,
       COUNT(*) AS n_articles,
       COUNT(DISTINCT source_id) AS n_sources
  FROM articles
 WHERE collected_at >= NOW() - INTERVAL '6 hours'
 GROUP BY 1 ORDER BY 1 DESC;

\echo
\echo === Quality of LAST 60 MINUTES of articles ===
WITH recent AS (
  SELECT * FROM articles
   WHERE collected_at >= NOW() - INTERVAL '60 minutes'
     AND substrate_status='ok'
)
SELECT
  (SELECT COUNT(*) FROM recent) AS articles_60m,
  (SELECT COUNT(*) FROM recent WHERE language_detected='en'
    AND title ~ '[ఀ-౿ऀ-ॿঀ-৿]') AS lang_mistag,
  (SELECT COUNT(*) FROM recent WHERE LENGTH(summary_executive) = 500) AS cliff_500,
  (SELECT COUNT(*) FROM recent WHERE labse_embedding IS NULL) AS no_embed,
  (SELECT ROUND(100.0 * COUNT(*) FILTER (WHERE LOWER(ac.subject_text) IN
     ('article','story','report','piece','news','we','they'))::numeric
     / GREATEST(COUNT(*), 1), 1)
     FROM article_claims ac JOIN recent r ON r.id = ac.article_id) AS placeholder_pct_60m,
  (SELECT COUNT(*) FROM article_events ae JOIN recent r ON r.id = ae.article_id
    WHERE ae.is_future = TRUE
      AND ae.effective_event_date < r.published_at::date - INTERVAL '60 days') AS is_future_bad;

\echo
\echo === Top 8 most-prolific new sources in last hour ===
SELECT s.name, a.language_detected AS lang, COUNT(*) AS n
  FROM articles a JOIN sources s ON s.id = a.source_id
 WHERE a.collected_at >= NOW() - INTERVAL '60 minutes'
 GROUP BY s.name, a.language_detected
 ORDER BY n DESC LIMIT 8;
