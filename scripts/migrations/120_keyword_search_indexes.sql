-- 120_keyword_search_indexes.sql
-- Trigram GIN indexes powering fast keyword/entity search for the Keyword Dossier.
-- Naive/regex search timed out on wide windows (verified 2026-07-06); pg_trgm makes
-- ILIKE / ~* fast. pg_trgm is already installed on this DB.
--
-- NOTE: on an existing (non-empty) DB, run each CREATE INDEX CONCURRENTLY manually
-- (they cannot run inside a transaction block). Sizes are modest: title/actor are
-- short columns; post_text is only ~50k rows. Disk checked (39G free) before build.

CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Article title: primary free-text keyword search path.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_articles_title_trgm
  ON articles USING gin (title gin_trgm_ops);

-- Social post text: keyword search across social_posts.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_social_posts_text_trgm
  ON social_posts USING gin (post_text gin_trgm_ops);

-- Stance actor: fast sentiment-distribution lookup by entity/keyword.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_article_stances_actor_trgm
  ON article_stances USING gin (actor gin_trgm_ops);
