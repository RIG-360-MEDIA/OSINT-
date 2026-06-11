-- 111: keep-all for YouTube clips.
--
-- Until now the YouTube pipeline only stored clips whose subject was one of the
-- ~64 monitored user_entities; every other newsworthy segment was discarded
-- (≈64% of processed videos yielded zero clips). This mirrors the article
-- corpus instead: store every newsworthy clip we already process, and turn the
-- watchlist into a TAG (is_watchlisted) rather than a hard ingest gate, so
-- relevance can be applied as a filter/score per view without losing the data.
--
-- Forward-only: existing 642 clips were all extracted under the watchlist gate,
-- so the column defaults to TRUE and is correct for them retroactively.
ALTER TABLE youtube_clips_v2
  ADD COLUMN IF NOT EXISTS is_watchlisted boolean NOT NULL DEFAULT true;

COMMENT ON COLUMN youtube_clips_v2.is_watchlisted IS
  'true = matched_entity is one of the monitored user_entities; '
  'false = newsworthy clip kept off-watchlist (keep-all mode, migration 111).';

-- Feed/relevance queries that want the old watched-only behaviour filter on
-- WHERE is_watchlisted; index keeps that cheap.
CREATE INDEX IF NOT EXISTS idx_youtube_clips_v2_watchlisted
  ON youtube_clips_v2 (is_watchlisted, created_at DESC);
