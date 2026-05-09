-- 051_newsroom_channels.sql
-- THE NEWSROOM — Phase 1 schema #1 of 7
--
-- Channel registry for the multi-channel TV/YouTube intelligence pillar
-- (`/clips` redesign). Distinct from `youtube_channels` (003_*) so the
-- existing /clips ingest pipeline stays untouched. Cross-reference is
-- via `yt_handle` (e.g. "@tv9telugulive") — newsroom uses HLS live pulls
-- + transcripts; youtube_channels uses video-id + transcript fetch.

CREATE TABLE IF NOT EXISTS newsroom_channels (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name          TEXT        NOT NULL,                  -- "TV9 Telugu"
    yt_handle     TEXT        NOT NULL UNIQUE,           -- "@tv9telugulive"
    language      TEXT        NOT NULL,                  -- 'te','hi','en'
    beat          TEXT        NOT NULL,                  -- 'telangana_politics', etc.
    is_live_24x7  BOOLEAN     NOT NULL DEFAULT FALSE,
    active        BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_newsroom_channels_active_live
    ON newsroom_channels (active, is_live_24x7)
    WHERE active = TRUE;

COMMENT ON TABLE newsroom_channels IS
    'THE NEWSROOM channel registry — Telugu/Hindi/English live + VOD sources for /clips redesign.';
