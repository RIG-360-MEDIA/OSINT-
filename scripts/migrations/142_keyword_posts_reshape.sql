-- 142_keyword_posts_reshape.sql
-- Phase 2 — keyword-collector persistence. Option A: REUSE + RESHAPE social_posts.
-- Verified against the live DB (rig-postgres) 2026-07-08. Idempotent.
-- social_posts is small (~57k rows) and these are nullable text columns, so
-- ADD COLUMN is an instant metadata-only change (PG16) — no rewrite, no lock pileup.

BEGIN;

-- Core keyword columns the collectors fill (everything else -> raw jsonb) --------
ALTER TABLE social_posts ADD COLUMN IF NOT EXISTS matched_keyword text;
ALTER TABLE social_posts ADD COLUMN IF NOT EXISTS author_username  text;
ALTER TABLE social_posts ADD COLUMN IF NOT EXISTS channel          text;
ALTER TABLE social_posts ADD COLUMN IF NOT EXISTS source           text;
ALTER TABLE social_posts ADD COLUMN IF NOT EXISTS full_content     text;
-- (all other core columns — platform, platform_post_id, post_text, post_url,
--  posted_at, likes, upvotes, comments_count, shares, views, upvote_ratio,
--  is_retweet, is_reply, lang, has_media, media_urls, raw — already exist.)

COMMENT ON COLUMN social_posts.matched_keyword IS 'Keyword query that surfaced this post (keyword-driven / Meltwater model).';
COMMENT ON COLUMN social_posts.author_username  IS 'Flat handle/channel/account. Replaces the social_authors FK for keyword posts.';
COMMENT ON COLUMN social_posts.channel          IS 'Telegram channel / YouTube channel name / WeChat account / subreddit.';
COMMENT ON COLUMN social_posts.source           IS 'Collector method that produced the row (tikwm, innertube, twscrape, t.me/s, sogou…).';
COMMENT ON COLUMN social_posts.full_content     IS 'Full body — WeChat article (~6k Chinese chars), future YT transcript. FTS-indexed. NULL for short-form.';

-- Dedup key — REQUIRED by the collector upsert -----------------------------------
-- ALREADY EXISTS on the live DB as social_posts_platform_platform_post_id_key.
-- Idempotent guard (no-op here; covers a fresh initdb apply):
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'social_posts'::regclass AND contype = 'u'
      AND conname  = 'social_posts_platform_platform_post_id_key'
  ) THEN
    ALTER TABLE social_posts
      ADD CONSTRAINT social_posts_platform_platform_post_id_key
      UNIQUE (platform, platform_post_id);
  END IF;
END $$;

-- Indexes ------------------------------------------------------------------------
-- (platform, posted_at DESC) already exists as idx_social_posts_platform — skipped.
CREATE INDEX IF NOT EXISTS idx_social_posts_matched_keyword
  ON social_posts (matched_keyword, platform, posted_at DESC)
  WHERE matched_keyword IS NOT NULL;

-- GIN on raw — query per-platform extras (subreddit, channel_id, hashtags, region…).
CREATE INDEX IF NOT EXISTS idx_social_posts_raw_gin
  ON social_posts USING gin (raw);

-- FTS on full_content. Trigram (gin_trgm_ops), NOT tsvector('simple'): it matches
-- the existing idx_social_posts_text_trgm pattern AND actually works for the
-- Chinese WeChat bodies (character n-grams) plus English YT transcripts; supports
-- ILIKE '%term%'. Partial — most (short-form) rows have NULL full_content.
CREATE INDEX IF NOT EXISTS idx_social_posts_full_content_trgm
  ON social_posts USING gin (full_content gin_trgm_ops)
  WHERE full_content IS NOT NULL;

-- Search audit table (persist-from-use) ------------------------------------------
CREATE TABLE IF NOT EXISTS keyword_searches (
  id           bigserial   PRIMARY KEY,
  keyword      text        NOT NULL,
  platform     varchar(16) NOT NULL,
  requested_at timestamptz NOT NULL DEFAULT now(),
  n_results    integer,
  took_ms      integer,
  client       text
);
CREATE INDEX IF NOT EXISTS idx_keyword_searches_keyword  ON keyword_searches (keyword,  requested_at DESC);
CREATE INDEX IF NOT EXISTS idx_keyword_searches_platform ON keyword_searches (platform, requested_at DESC);

COMMIT;
