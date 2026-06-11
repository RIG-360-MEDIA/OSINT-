-- 112: priority queue for YouTube transcript fetching.
--
-- The relay was FIFO (ORDER BY discovered_at) so fresh political news waited
-- behind the whole backlog and went stale. Now: political/watched-entity videos
-- are fetched FIRST, then newest-first. is_political is set at discovery from the
-- title (high-recall match against watched entities + political terms) and is
-- NEVER deprioritised or aged out.
ALTER TABLE pending_youtube_videos
  ADD COLUMN IF NOT EXISTS is_political boolean NOT NULL DEFAULT false;

CREATE INDEX IF NOT EXISTS idx_pyv_priority
  ON pending_youtube_videos (status, is_political DESC, video_published_at DESC);

COMMENT ON COLUMN pending_youtube_videos.is_political IS
  'Title mentions a watched entity / political term — top transcript priority, '
  'never deprioritised or aged out (migration 112).';
