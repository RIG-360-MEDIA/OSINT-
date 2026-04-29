-- 032_drop_unused_coverage_indexes.sql
--
-- Coverage audit (2026-04-28) C-3: pg_stat_user_indexes shows two indexes
-- on `articles` with idx_scan = 0 since boot:
--
--   - idx_articles_topic           (topic_category, collected_at DESC)
--                                  WHERE topic_category IS NOT NULL
--   - idx_articles_updated_at      (updated_at DESC) WHERE nlp_processed = true
--
-- Neither is referenced by the live coverage_router queries (which filter
-- by user_article_relevance + a.id) nor by the brief generator.
-- They occupy ~1.6 MB and are written on every UPDATE / INSERT, so
-- removing them is a small but real write-amplification win.
--
-- Idempotent: DROP INDEX IF EXISTS.
-- Safe to re-add later (CREATE INDEX CONCURRENTLY) if a query pattern
-- emerges that benefits from them.

DROP INDEX IF EXISTS public.idx_articles_topic;
DROP INDEX IF EXISTS public.idx_articles_updated_at;
