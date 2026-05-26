-- THE NEWSROOM — per-channel live digest (always-on, cheap, captions-driven).
--
-- Updated every ~60 s by `tasks.newsroom.live_captions_poll` (which
-- pulls YT auto-captions for the channel's current_live_video_id) and
-- `tasks.newsroom.digest_live_channel` (which asks Cerebras for the
-- top phrases / stories / entities mentioned in the last caption window).
--
-- Idempotent: one row per channel, upserted in place.

CREATE TABLE IF NOT EXISTS newsroom_channel_live_digest (
  channel_id        UUID         PRIMARY KEY
                                 REFERENCES newsroom_channels(id) ON DELETE CASCADE,
  video_id          TEXT         NOT NULL,
  caption_buffer    TEXT         NOT NULL DEFAULT '',
  last_caption_at   TIMESTAMPTZ,
  top_phrases       JSONB        NOT NULL DEFAULT '[]'::jsonb,
  top_stories       JSONB        NOT NULL DEFAULT '[]'::jsonb,
  summary           TEXT         NOT NULL DEFAULT '',
  entity_ids        UUID[]       NOT NULL DEFAULT '{}',
  generated_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_newsroom_live_digest_generated
  ON newsroom_channel_live_digest (generated_at DESC);

CREATE INDEX IF NOT EXISTS idx_newsroom_live_digest_entities
  ON newsroom_channel_live_digest USING GIN (entity_ids);
