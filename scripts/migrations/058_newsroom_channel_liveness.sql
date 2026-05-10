-- 058_newsroom_channel_liveness.sql
-- Liveness state on newsroom_channels — driven by tasks.newsroom.check_liveness
-- (every 5 min). Used by WALL to show "LIVE NOW" red badge + a Watch Live
-- button on tiles whose channel is currently streaming.

ALTER TABLE newsroom_channels
    ADD COLUMN IF NOT EXISTS current_live_video_id   TEXT,
    ADD COLUMN IF NOT EXISTS current_live_title      TEXT,
    ADD COLUMN IF NOT EXISTS last_live_check_at      TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS last_live_at            TIMESTAMPTZ;

COMMENT ON COLUMN newsroom_channels.current_live_video_id IS
    'YouTube video id of the channel''s currently-live broadcast, NULL if not live. Refreshed every 5 min by tasks.newsroom.check_liveness.';
COMMENT ON COLUMN newsroom_channels.last_live_at IS
    'Most recent timestamp at which the channel was observed live. Persists across non-live windows.';
