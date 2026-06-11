-- ============================================================================
-- Migration 109 — youtube_channels table
-- ============================================================================
-- Registry of YouTube channels the discovery task monitors. The Celery
-- discover_youtube_channels task reads active=TRUE rows, runs RSS discovery
-- for each, and upserts new videos into pending_youtube_videos.
--
-- Idempotent — safe to re-run.
-- ============================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS youtube_channels (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    channel_id          TEXT        NOT NULL UNIQUE,   -- UC… YouTube channel id
    channel_name        TEXT        NOT NULL,
    language            VARCHAR(8)  NOT NULL DEFAULT 'te', -- primary language: te/hi/en
    tier                VARCHAR(20) NOT NULL DEFAULT 'telangana',
                                    -- telangana | india | global
    active              BOOLEAN     NOT NULL DEFAULT TRUE,
    last_discovered_at  TIMESTAMPTZ,                   -- updated per discovery run
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS youtube_channels_active_idx
  ON youtube_channels (active, last_discovered_at)
  WHERE active = TRUE;

COMMENT ON TABLE youtube_channels IS
  'Registry of monitored YouTube channels. discover_youtube_channels Celery task '
  'reads active=TRUE rows every 30 min and upserts new videos into pending_youtube_videos.';

-- ── Seed: Telangana tier (confirmed channel IDs only) ────────────────────────
-- Add more via:
--   INSERT INTO youtube_channels (channel_id, channel_name, language, tier)
--   VALUES ('UC...', 'Channel Name', 'te', 'telangana')
--   ON CONFLICT (channel_id) DO NOTHING;

INSERT INTO youtube_channels (channel_id, channel_name, language, tier)
VALUES
    ('UCDCMjD1XIAsCZsYHNMGVcog', 'V6 News',      'te', 'telangana')
ON CONFLICT (channel_id) DO NOTHING;

-- ── Placeholder rows (channel IDs unverified — update before activating) ─────
-- Run: SELECT channel_id, channel_name FROM youtube_channels WHERE active=FALSE
-- to see what needs verifying, then:
--   UPDATE youtube_channels SET channel_id='UC<verified>', active=TRUE WHERE channel_name='...';
INSERT INTO youtube_channels (channel_id, channel_name, language, tier, active)
VALUES
    ('VERIFY_TV9_TELUGU',       'TV9 Telugu',        'te', 'telangana', FALSE),
    ('VERIFY_NTV_TELUGU',       'NTV Telugu',        'te', 'telangana', FALSE),
    ('VERIFY_ABN_ANDHRAJYOTHI', 'ABN Andhrajyothi',  'te', 'telangana', FALSE),
    ('VERIFY_SAKSHI_TV',        'Sakshi TV',          'te', 'telangana', FALSE),
    ('VERIFY_10TV',             '10TV News Telugu',   'te', 'telangana', FALSE),
    ('VERIFY_HMTV',             'HMTV News',          'te', 'telangana', FALSE),
    ('VERIFY_T_NEWS',           'T News',             'te', 'telangana', FALSE),
    ('VERIFY_ETV_TELANGANA',    'ETV Telangana',      'te', 'telangana', FALSE),
    ('VERIFY_AAJ_TAK',          'Aaj Tak',            'hi', 'india',     FALSE),
    ('VERIFY_ABP_NEWS',         'ABP News',           'hi', 'india',     FALSE),
    ('VERIFY_NDTV_INDIA',       'NDTV India',         'hi', 'india',     FALSE),
    ('VERIFY_INDIA_TODAY',      'India Today',        'en', 'india',     FALSE),
    ('VERIFY_WION',             'WION',               'en', 'global',    FALSE)
ON CONFLICT (channel_id) DO NOTHING;

COMMIT;

-- ============================================================================
-- VERIFY:
--   SELECT channel_id, channel_name, active FROM youtube_channels ORDER BY tier, language;
-- ADD VERIFIED CHANNELS:
--   UPDATE youtube_channels SET channel_id='UCxxxxxx', active=TRUE
--    WHERE channel_name = 'TV9 Telugu';
-- ============================================================================
