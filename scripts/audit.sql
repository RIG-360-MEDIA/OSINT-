\echo === Story Threads (P11) ===
SELECT COUNT(*) AS total, COUNT(*) FILTER (WHERE escalating) AS escalating FROM story_threads;
\echo
\echo === Newspaper Clippings (P16) ===
SELECT COUNT(*) AS total FROM newspaper_clippings;
\echo
\echo === Social signal tables (P17) ===
SELECT 'social_posts' AS t, COUNT(*) FROM social_posts UNION ALL
SELECT 'social_monitors', COUNT(*) FROM social_monitors UNION ALL
SELECT 'social_sentiment_daily', COUNT(*) FROM social_sentiment_daily;
\echo
\echo === Govt source health summary ===
SELECT
  COUNT(*) FILTER (WHERE is_active) AS active,
  COUNT(*) FILTER (WHERE NOT is_active) AS inactive,
  COUNT(*) FILTER (WHERE health_score >= 0.9) AS healthy,
  COUNT(*) FILTER (WHERE consecutive_failures > 0) AS failing,
  COUNT(*) FILTER (WHERE last_scraped_at IS NULL) AS never_scraped
FROM govt_document_sources;
\echo
\echo === Top 3 Story Threads ===
SELECT LEFT(title, 70) AS title, article_count, escalating FROM story_threads ORDER BY article_count DESC LIMIT 3;
\echo
\echo === Top 3 Coverage articles for the user ===
SELECT LEFT(a.title, 60) AS title, a.source_name, ROUND(r.score_final::numeric,2) AS score, r.relevance_tier AS tier
FROM user_article_relevance r
JOIN articles a ON a.id = r.article_id
WHERE r.user_id = (SELECT id FROM users WHERE email='pranavpuri03@gmail.com')
ORDER BY r.score_final DESC LIMIT 3;
\echo
\echo === Top 3 YouTube clips ===
SELECT LEFT(video_title, 50) AS clip, channel_title, importance, matched_entity FROM youtube_clips ORDER BY collected_at DESC LIMIT 3;
\echo
\echo === Pipeline backlogs ===
SELECT 'unembedded_articles' AS metric, COUNT(*) AS n FROM articles WHERE labse_embedding IS NULL AND nlp_processed
UNION ALL SELECT 'pending_nlp_articles', COUNT(*) FROM articles WHERE NOT nlp_processed
UNION ALL SELECT 'unscored_govt_docs', COUNT(*) FROM govt_documents WHERE intrinsic_importance = 0;
\echo
\echo === Active sources scrape lag ===
SELECT
  CASE
    WHEN last_scraped_at IS NULL THEN 'never'
    WHEN last_scraped_at > NOW() - INTERVAL '1 hour' THEN 'last_hour'
    WHEN last_scraped_at > NOW() - INTERVAL '6 hours' THEN 'last_6h'
    WHEN last_scraped_at > NOW() - INTERVAL '24 hours' THEN 'last_24h'
    ELSE 'older'
  END AS bucket,
  COUNT(*) AS n
FROM govt_document_sources WHERE is_active = TRUE
GROUP BY bucket ORDER BY bucket;
