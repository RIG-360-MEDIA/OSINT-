-- 057_newsroom_briefs.sql
-- THE NEWSROOM — Phase 1 schema #7 of 7  (Phase 8 storage layer)
--
-- Daily NEWSROOM digest: 5–7 anchored stories pulled from the day's
-- broadcasts. Generated 06:00 IST by tasks.newsroom.generate_daily_brief
-- (Cerebras call composes headline + 2-paragraph summary for each story).
--
-- Stories live as JSONB so the schema doesn't churn while we iterate
-- on the digest format. Each story:
--   { "headline": str, "summary": str, "source_segment_ids": [uuid, ...] }
--
-- One row per (date) — globally shared digest, not per-user. Idempotent:
-- the brief task overwrites the row for `for_date` rather than inserting
-- a new one, so re-running the cron is safe.

CREATE TABLE IF NOT EXISTS newsroom_briefs (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    for_date        DATE        NOT NULL UNIQUE,         -- IST calendar day
    generated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- 5–7 stories, JSONB array. Schema documented above.
    stories         JSONB       NOT NULL DEFAULT '[]'::jsonb,

    -- Stats for telemetry
    story_count     INTEGER     NOT NULL DEFAULT 0,
    source_channel_count INTEGER NOT NULL DEFAULT 0,
    source_segment_count INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_newsroom_briefs_recent
    ON newsroom_briefs (for_date DESC);

COMMENT ON TABLE newsroom_briefs IS
    'Daily NEWSROOM digest — generated 06:00 IST by tasks.newsroom.generate_daily_brief.';
