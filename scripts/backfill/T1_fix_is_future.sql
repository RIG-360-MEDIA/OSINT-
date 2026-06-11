-- T1: Fix is_future contradictions
-- Pre-flight → backup → UPDATE → gate

\echo === Pre-flight count (expect ~7825) ===
SELECT COUNT(*) AS contradictions
  FROM article_events ae JOIN articles a ON a.id=ae.article_id
 WHERE ae.is_future=TRUE
   AND ae.effective_event_date IS NOT NULL
   AND ae.effective_event_date < a.published_at::date - INTERVAL '60 days';

\echo
\echo === Backup table ===
DROP TABLE IF EXISTS article_events_is_future_backup_20260523;
CREATE TABLE article_events_is_future_backup_20260523 AS
SELECT ae.id, ae.is_future AS old_is_future,
       ae.effective_event_date, a.published_at::date AS published_date
  FROM article_events ae JOIN articles a ON a.id=ae.article_id
 WHERE ae.is_future=TRUE
   AND ae.effective_event_date IS NOT NULL
   AND ae.effective_event_date < a.published_at::date - INTERVAL '60 days';
SELECT COUNT(*) AS backed_up FROM article_events_is_future_backup_20260523;

\echo
\echo === UPDATE (flip is_future TRUE -> FALSE for past dates) ===
UPDATE article_events ae
   SET is_future = FALSE
  FROM articles a
 WHERE ae.article_id=a.id
   AND ae.is_future=TRUE
   AND ae.effective_event_date IS NOT NULL
   AND ae.effective_event_date < a.published_at::date - INTERVAL '60 days';

\echo
\echo === Gate (must be 0) ===
SELECT COUNT(*) AS post_contradictions
  FROM article_events ae JOIN articles a ON a.id=ae.article_id
 WHERE ae.is_future=TRUE
   AND ae.effective_event_date IS NOT NULL
   AND ae.effective_event_date < a.published_at::date - INTERVAL '60 days';
