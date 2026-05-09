-- 052_newsroom_broadcasts.sql
-- THE NEWSROOM — Phase 1 schema #2 of 7
--
-- One row per broadcast (live stream window or VOD). A 24×7 channel
-- creates a new broadcast row each time the live stream goes up; a
-- VOD ingestion creates one row per video. Segments belong to a
-- broadcast, not directly to a channel, so we can answer "what was
-- on at 8 PM yesterday" cleanly.

CREATE TABLE IF NOT EXISTS newsroom_broadcasts (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    channel_id      UUID        NOT NULL REFERENCES newsroom_channels(id) ON DELETE CASCADE,
    yt_video_id     TEXT        NOT NULL,
    title           TEXT,
    title_en        TEXT,                                -- inline translated
    started_at      TIMESTAMPTZ NOT NULL,
    ended_at        TIMESTAMPTZ,
    is_live         BOOLEAN     NOT NULL DEFAULT FALSE,
    duration_sec    INTEGER,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (channel_id, yt_video_id)
);

CREATE INDEX IF NOT EXISTS idx_newsroom_broadcasts_channel_started
    ON newsroom_broadcasts (channel_id, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_newsroom_broadcasts_live
    ON newsroom_broadcasts (is_live, started_at DESC)
    WHERE is_live = TRUE;

COMMENT ON TABLE newsroom_broadcasts IS
    'Per-broadcast metadata — one row per live stream window or VOD ingest.';
