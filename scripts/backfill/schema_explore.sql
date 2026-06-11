\echo === All v3-OK fields we can show ===
SELECT
  COUNT(*) FILTER (WHERE register_is_breaking=TRUE) AS breaking_now,
  COUNT(*) FILTER (WHERE register_emotion IS NOT NULL) AS with_emotion,
  COUNT(*) FILTER (WHERE register_style IS NOT NULL) AS with_style,
  COUNT(*) FILTER (WHERE full_text_translated IS NOT NULL) AS translated,
  COUNT(*) FILTER (WHERE collected_at >= NOW() - INTERVAL '24h') AS today
  FROM articles WHERE substrate_status='ok';

\echo
\echo === Article types ===
SELECT article_type, COUNT(*) AS n FROM articles
 WHERE substrate_status='ok'
 GROUP BY 1 ORDER BY 2 DESC LIMIT 12;

\echo
\echo === Entity dictionary breakdown ===
SELECT entity_type, COUNT(*) AS n
  FROM entity_dictionary GROUP BY 1 ORDER BY 2 DESC LIMIT 10;

\echo
\echo === Top quoted speakers ===
SELECT LOWER(TRIM(speaker_name)) AS speaker, COUNT(*) AS n
  FROM article_quotes
 WHERE speaker_name IS NOT NULL AND LENGTH(TRIM(speaker_name)) > 2
 GROUP BY 1 ORDER BY 2 DESC LIMIT 12;

\echo
\echo === Top countries / locations ===
SELECT country, COUNT(*) AS n FROM article_locations
 WHERE country IS NOT NULL GROUP BY 1 ORDER BY 2 DESC LIMIT 10;

\echo
\echo === Stance distribution ===
SELECT stance, COUNT(*) AS n
  FROM article_stances WHERE stance IS NOT NULL
 GROUP BY 1 ORDER BY 2 DESC LIMIT 8;

\echo
\echo === Story threads (escalating) ===
SELECT COUNT(*) AS total_threads,
       COUNT(*) FILTER (WHERE escalating=TRUE) AS escalating
  FROM story_threads;

\echo
\echo === Breaking news in last 24h ===
SELECT LEFT(title, 80) AS title, primary_subject
  FROM articles
 WHERE register_is_breaking=TRUE
   AND collected_at >= NOW() - INTERVAL '24h'
 ORDER BY collected_at DESC LIMIT 8;

\echo
\echo === Per-language ingest last 24h ===
SELECT language_detected AS lang, COUNT(*) AS n
  FROM articles
 WHERE collected_at >= NOW() - INTERVAL '24h'
 GROUP BY 1 ORDER BY 2 DESC LIMIT 12;

\echo
\echo === Recent contradictions ===
SELECT COUNT(*) AS total, COUNT(*) FILTER (WHERE detected_at >= NOW() - INTERVAL '7 days') AS last_7d
  FROM article_contradictions;
