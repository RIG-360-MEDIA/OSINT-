-- ============================================================
-- Migration 047 — chat-room column + top_stories_daily cache
-- ============================================================
-- Two small additions to power the new article-page features:
--
-- 1. analyst_sessions / analyst_turns gain a `room` column so the
--    Ask Bar on /coverage/articles can persist conversations into
--    the same tables as /analyst, discriminated by room='coverage'.
--    Default 'analyst' so legacy rows stay correct.
--
-- 2. top_stories_daily caches the Top-5 chain-of-thought summaries
--    for the day, refreshed every 6h. Keyed by (date, user_id) when
--    user-personalised, NULL user_id for the global fallback.
--
-- Idempotent — safe to re-run.
-- ============================================================

-- ── 1. room discriminator on chat tables ────────────────────
-- Tables created by an earlier migration; guard with information_schema
-- so this file works even if those tables haven't shipped yet.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_name = 'analyst_sessions'
    ) THEN
        EXECUTE 'ALTER TABLE analyst_sessions
                 ADD COLUMN IF NOT EXISTS room TEXT NOT NULL DEFAULT ''analyst''';
        EXECUTE 'CREATE INDEX IF NOT EXISTS analyst_sessions_room_user_idx
                 ON analyst_sessions (room, user_id, updated_at DESC)';
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_name = 'analyst_turns'
    ) THEN
        EXECUTE 'ALTER TABLE analyst_turns
                 ADD COLUMN IF NOT EXISTS room TEXT NOT NULL DEFAULT ''analyst''';
        EXECUTE 'CREATE INDEX IF NOT EXISTS analyst_turns_room_session_idx
                 ON analyst_turns (room, session_id, created_at DESC)';
    END IF;
END$$;


-- ── 2. top_stories_daily cache ──────────────────────────────
CREATE TABLE IF NOT EXISTS top_stories_daily (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    date                DATE        NOT NULL,
    -- NULL = global fallback Top-5; non-NULL = personalised per user.
    user_id             UUID,
    -- Ordered list of { article_id, why_matters: "...", score: 0.0 }.
    stories             JSONB       NOT NULL,
    generated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    generated_by_model  TEXT        NOT NULL DEFAULT 'llama-3.3-70b-versatile',
    UNIQUE (date, user_id)
);

CREATE INDEX IF NOT EXISTS top_stories_daily_user_date_idx
  ON top_stories_daily (user_id, date DESC);

COMMENT ON TABLE top_stories_daily IS
  'Cache for Top-5 stories on /coverage/articles. Refreshed every 6h. user_id NULL = global fallback.';


-- ── Coverage gaps cache ─────────────────────────────────────
CREATE TABLE IF NOT EXISTS coverage_gaps_daily (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    detected_for_date   DATE        NOT NULL,
    entity_id           UUID        NOT NULL
                                    REFERENCES entity_dictionary(id) ON DELETE CASCADE,
    social_volume_7d    INTEGER     NOT NULL DEFAULT 0,
    article_volume_7d   INTEGER     NOT NULL DEFAULT 0,
    -- social/article ratio.
    ratio               REAL        NOT NULL DEFAULT 0.0,
    -- One-line Groq summary: "what social is saying that articles aren't".
    summary             TEXT        NOT NULL DEFAULT '',
    detected_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (detected_for_date, entity_id)
);

CREATE INDEX IF NOT EXISTS coverage_gaps_date_ratio_idx
  ON coverage_gaps_daily (detected_for_date DESC, ratio DESC);

COMMENT ON TABLE coverage_gaps_daily IS
  'Daily snapshot of entities heavy in social but light in articles. Powers Coverage gaps panel.';
