\echo === Total claims last 24h, sources collected_at ===
SELECT COUNT(*) AS claims_total,
       COUNT(*) FILTER (WHERE LOWER(TRIM(ac.subject_text)) NOT IN
              ('article','story','report','piece','news','we','they','officials')) AS non_placeholder,
       MIN(a.collected_at) AS oldest, MAX(a.collected_at) AS newest
  FROM article_claims ac JOIN articles a ON a.id=ac.article_id
 WHERE a.collected_at >= NOW() - INTERVAL '24 hours';

\echo === Top non-placeholder subjects last 24h (RAW count) ===
SELECT LOWER(TRIM(ac.subject_text)) AS entity, COUNT(*) AS n
  FROM article_claims ac JOIN articles a ON a.id=ac.article_id
 WHERE a.collected_at >= NOW() - INTERVAL '24 hours'
   AND LENGTH(TRIM(ac.subject_text)) BETWEEN 3 AND 80
   AND LOWER(TRIM(ac.subject_text)) NOT IN
       ('article','story','report','piece','news','we','they','officials')
 GROUP BY 1 ORDER BY 2 DESC LIMIT 10;
