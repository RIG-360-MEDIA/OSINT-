-- analytics.api_clip_grants — the strict on-demand gate for YouTube transcripts.
--
-- A row records that an org was shown a clip by one of its keyword/entity queries
-- (keyword-sentiment, /analytics/sentiment?include_youtube, or entity coverage).
-- GET /v1/clips/{id} serves a transcript ONLY when a fresh grant exists, so YouTube
-- stays keyword-driven: a client can read the transcript of a clip its own query
-- surfaced, and nothing else. Grants are refreshed (surfaced_at=now()) on every
-- re-surface and read within a rolling window (OSINT_CLIP_GRANT_WINDOW_HOURS, 24h).
CREATE TABLE IF NOT EXISTS analytics.api_clip_grants (
    org_id      uuid        NOT NULL,
    clip_id     text        NOT NULL,   -- youtube_clips_v2.id::text (the id handed to the client)
    surfaced_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, clip_id)
);

CREATE INDEX IF NOT EXISTS idx_api_clip_grants_fresh
    ON analytics.api_clip_grants (org_id, surfaced_at DESC);
