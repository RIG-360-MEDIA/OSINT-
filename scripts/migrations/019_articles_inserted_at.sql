-- Migration 019: add `inserted_at` to articles
--
-- Why: collectors overload `collected_at` with the feed entry's published date,
-- so insert-time queries (e.g. "rows added in last 15 min") get fooled when
-- articles are republished with old timestamps. `inserted_at` records the
-- actual DB insert time independently of feed metadata.
--
-- Strategy:
--   1. Add column nullable so existing rows aren't touched
--   2. Backfill from `collected_at` (best available approximation)
--   3. Set DEFAULT NOW() and NOT NULL for future inserts
--   4. Index for time-window queries

BEGIN;

ALTER TABLE articles
    ADD COLUMN IF NOT EXISTS inserted_at TIMESTAMPTZ;

UPDATE articles
   SET inserted_at = collected_at
 WHERE inserted_at IS NULL;

ALTER TABLE articles
    ALTER COLUMN inserted_at SET DEFAULT NOW();

ALTER TABLE articles
    ALTER COLUMN inserted_at SET NOT NULL;

CREATE INDEX IF NOT EXISTS idx_articles_inserted_at
    ON articles (inserted_at DESC);

COMMIT;
