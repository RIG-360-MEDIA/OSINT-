\echo === Today top 5 by raw count (what we show now) ===
WITH today AS (
  SELECT entity_text, SUM(n_mentions_total) AS n
    FROM entity_mention_daily WHERE date >= CURRENT_DATE - 1 GROUP BY entity_text
)
SELECT entity_text, n FROM today ORDER BY n DESC LIMIT 5;

\echo
\echo === Top 12 by SURGE RATIO (real surges) ===
WITH today AS (
  SELECT entity_text, SUM(n_mentions_total) AS today_n
    FROM entity_mention_daily WHERE date >= CURRENT_DATE - 1 GROUP BY entity_text
),
baseline AS (
  SELECT entity_text, AVG(n_mentions_total)::numeric AS avg_n
    FROM entity_mention_daily
   WHERE date BETWEEN CURRENT_DATE - 8 AND CURRENT_DATE - 2 GROUP BY entity_text
)
SELECT t.entity_text, t.today_n, ROUND(COALESCE(b.avg_n, 0), 1) AS avg_baseline,
       CASE WHEN b.avg_n > 0 THEN ROUND((t.today_n/b.avg_n)::numeric, 1) ELSE NULL END AS surge_ratio
  FROM today t LEFT JOIN baseline b USING(entity_text)
 WHERE t.today_n >= 5 AND b.avg_n > 0
 ORDER BY (t.today_n/b.avg_n) DESC LIMIT 12;

\echo
\echo === How many entities have any baseline history? ===
SELECT COUNT(DISTINCT entity_text) AS with_baseline FROM entity_mention_daily
 WHERE date BETWEEN CURRENT_DATE - 8 AND CURRENT_DATE - 2;
SELECT COUNT(DISTINCT entity_text) AS total_entities FROM entity_mention_daily;

\echo
\echo === Date range coverage ===
SELECT MIN(date) AS earliest, MAX(date) AS latest, COUNT(DISTINCT date) AS distinct_days FROM entity_mention_daily;
